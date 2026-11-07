"""One suite per task: load its labelled cases, run them through the real service in
the eval workspace, grade them in code.

`run` returns one row per case; `grade` turns the rows into a score, whether it passes
(None while the task has no threshold), and a breakdown that helps read the score.
Grading reads what the app's own checks produced, so a suite measures what the user
would see.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.harness import NO_BUDGET, Workspace
from jobingo.domain.text import fold
from jobingo.llm.client import LLMCallError, LLMClient, Tier
from jobingo.llm.journal import run_task
from jobingo.llm.tasks.draft_letter import DRAFT_LETTER_TASK
from jobingo.llm.tasks.extract_offer import EXTRACT_OFFER_TASK, ExtractOfferInput
from jobingo.llm.tasks.score_offer import SCORE_OFFER_TASK
from jobingo.llm.tasks.select_cv_content import SELECT_CV_CONTENT_TASK
from jobingo.services.applications import apply_to_offer
from jobingo.services.cv_proposal import OfferText, propose_cv
from jobingo.services.letters import propose_letter, set_company_notes
from jobingo.services.scoring import score_offer

CASES_DIR = Path(__file__).resolve().parent / "cases"

type Row = dict[str, Any]


def load_cases(name: str) -> list[dict[str, Any]]:
    """JSON lines; a line starting with `//` is a comment."""
    lines = (CASES_DIR / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip() and not line.startswith("//")]


@dataclass(frozen=True)
class Suite:
    name: str
    metric: str  # what `score` measures, for the observability page
    tier: Tier
    prompt_version: int
    threshold: float | None
    run: Callable[[Workspace, LLMClient, list[dict[str, Any]]], list[Row]]
    grade: Callable[[list[Row]], dict[str, Any]]


# --- select_cv_content -------------------------------------------------------------


def run_select_cv(ws: Workspace, client: LLMClient, cases: list[dict[str, Any]]) -> list[Row]:
    rows: list[Row] = []
    for case in cases:
        offer = case["offer"]
        row: Row = {"id": case["id"], "offer": offer["title"]}
        try:
            tailored, _ = propose_cv(
                ws.conn,
                client,
                NO_BUDGET,
                ws.user_id,
                "fr",
                OfferText(
                    title=offer["title"],
                    company=offer["company_name"],
                    description=offer["description_md"],
                ),
                style=ws.style,
            )
        except LLMCallError as exc:
            rows.append(row | {"passed": False, "error": str(exc)})
            continue
        kept = tailored.kept_items()
        kept_ids = {item.id for item in kept}
        missing = [i for i in case.get("must_keep", []) if i not in kept_ids]
        unwanted = [i for i in case.get("must_drop", []) if i in kept_ids]
        rows.append(
            row
            | {
                "passed": not missing and not unwanted,
                "missing": missing,
                "unwanted": unwanted,
                "refused_rewrites": [
                    f"{item.id}: {item.rejected_reason}" for item in kept if item.rejected_reason
                ],
                "accepted_rewrites": sum(item.rewritten for item in kept),
                "warnings": tailored.warnings,
            }
        )
    return rows


def grade_select_cv(rows: list[Row]) -> dict[str, Any]:
    passed = sum(bool(row["passed"]) for row in rows)
    return {
        "score": round(passed / len(rows), 3) if rows else None,
        "detail": {
            "cases": f"{passed}/{len(rows)}",
            "refused_rewrites": sum(len(row.get("refused_rewrites", [])) for row in rows),
            "accepted_rewrites": sum(row.get("accepted_rewrites", 0) for row in rows),
        },
    }


# --- extract_offer --------------------------------------------------------------------

# Compared exactly: the objectives' filters match these values.
_EXACT_FIELDS = ("contract", "remote")
# Compared loosely: « Ingénieur (H/F) » is « Ingénieur ».
_LOOSE_FIELDS = ("title", "company_name", "location")


def _norm(value: object) -> str:
    return " ".join(fold(str(value or "")).split())


def _field_ok(name: str, expected: object, got: object) -> bool:
    want, have = _norm(expected), _norm(got)
    if name in _EXACT_FIELDS or not want or not have:
        return want == have
    return want in have or have in want


def run_extract(ws: Workspace, client: LLMClient, cases: list[dict[str, Any]]) -> list[Row]:
    """The model alone, case by case: storing would merge offers across cases."""
    rows: list[Row] = []
    for case in cases:
        row: Row = {"id": case["id"]}
        try:
            output, _ = run_task(
                ws.conn,
                client,
                NO_BUDGET,
                ws.user_id,
                EXTRACT_OFFER_TASK,
                ExtractOfferInput(text=case["text"]),
                redaction_values=[],
            )
        except LLMCallError as exc:
            rows.append(row | {"passed": False, "fields_ok": 0, "fields": 1, "error": str(exc)})
            continue
        expected = case["expected"]["offers"]
        checked = ok = 0
        misses: list[str] = []
        for want, got in zip(expected, output.offers, strict=False):
            for name in _EXACT_FIELDS + _LOOSE_FIELDS:
                if name not in want:
                    continue
                checked += 1
                if _field_ok(name, want[name], getattr(got, name)):
                    ok += 1
                else:
                    misses.append(f"{name}: {want[name]!r} != {getattr(got, name)!r}")
        count_ok = len(output.offers) == len(expected)
        rows.append(
            row
            | {
                "passed": count_ok and ok == checked,
                "fields_ok": ok,
                "fields": max(checked, 1),
                "count_ok": count_ok,
                "misses": misses,
            }
        )
    return rows


def grade_extract(rows: list[Row]) -> dict[str, Any]:
    ok = sum(row["fields_ok"] for row in rows)
    total = sum(row["fields"] for row in rows)
    return {
        "score": round(ok / total, 3) if total else None,
        "detail": {
            "fields": f"{ok}/{total}",
            "offer_count_ok": f"{sum(bool(r.get('count_ok')) for r in rows)}/{len(rows)}",
        },
    }


# --- score_offer ------------------------------------------------------------------------

# Inherited from the POC as a policy, not as a score: the ranking must agree with the
# hand-made one at least this well.
SCORE_THRESHOLD = 0.85


def _ranks(values: list[float]) -> list[float]:
    """1-based ranks, highest value first, ties sharing their average rank."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(expected_ranks: list[float], scores: list[float]) -> float:
    """The rank correlation between the hand-made ranking (1 is the best) and the
    scores. Both are ranked again, so a failed case leaving a gap changes nothing."""
    want = _ranks([-rank for rank in expected_ranks])
    got = _ranks(scores)
    mean_a, mean_b = sum(want) / len(want), sum(got) / len(got)
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(want, got, strict=True))
    var_a = sum((a - mean_a) ** 2 for a in want)
    var_b = sum((b - mean_b) ** 2 for b in got)
    return cov / (var_a * var_b) ** 0.5 if var_a and var_b else 0.0


def _insert_offer(ws: Workspace, offer: dict[str, Any]) -> int:
    row = ws.conn.execute(
        """
        INSERT INTO offers (user_id, title, company_name, location, contract, remote,
            salary_min, salary_max, description_md, dedup_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (
            ws.user_id,
            offer["title"],
            offer.get("company_name", ""),
            offer.get("location", ""),
            offer.get("contract", ""),
            offer.get("remote", ""),
            offer.get("salary_min"),
            offer.get("salary_max"),
            offer.get("description_md", ""),
            uuid.uuid4().hex,
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def run_score(ws: Workspace, client: LLMClient, cases: list[dict[str, Any]]) -> list[Row]:
    rows: list[Row] = []
    for case in cases:
        row: Row = {"id": case["id"], "expected_rank": case["rank"]}
        try:
            score = score_offer(
                ws.conn, client, NO_BUDGET, ws.user_id, _insert_offer(ws, case["offer"])
            )
        except LLMCallError as exc:
            rows.append(row | {"passed": False, "score": None, "error": str(exc)})
            continue
        rows.append(
            row
            | {
                # A case fails alone only when it could not be scored; the suite is
                # graded on the whole ranking.
                "passed": score.score is not None,
                "score": score.score,
                "criteria": score.criteria.model_dump() if score.criteria else None,
                "summary": score.summary,
            }
        )
    return rows


def grade_score(rows: list[Row]) -> dict[str, Any]:
    scored = [row for row in rows if row["score"] is not None]
    rho = (
        spearman([r["expected_rank"] for r in scored], [r["score"] for r in scored])
        if len(scored) > 1
        else None
    )
    return {
        "score": round(rho, 3) if rho is not None else None,
        "detail": {
            "scored": f"{len(scored)}/{len(rows)}",
            "by_expected_rank": " ".join(
                f"{r['expected_rank']}:{r['score']}"
                for r in sorted(scored, key=lambda r: r["expected_rank"])
            ),
        },
    }


# --- draft_letter -----------------------------------------------------------------------


def run_letter(ws: Workspace, client: LLMClient, cases: list[dict[str, Any]]) -> list[Row]:
    rows: list[Row] = []
    for case in cases:
        application = apply_to_offer(ws.conn, ws.user_id, _insert_offer(ws, case["offer"]))
        assert application is not None
        set_company_notes(ws.conn, ws.user_id, application.id, case.get("notes", ""))
        row: Row = {"id": case["id"]}
        try:
            letter = propose_letter(ws.conn, client, NO_BUDGET, ws.user_id, application.id)
        except LLMCallError as exc:
            rows.append(row | {"passed": False, "error": str(exc)})
            continue
        assert letter is not None
        refused = [f"{s.name}: {s.rejected_reason}" for s in letter.slots if s.rejected_reason]
        empty = [s.name for s in letter.slots if not s.text and not s.rejected_reason]
        rows.append(
            row
            | {
                "passed": not refused and not empty,
                "refused": refused,
                "empty": empty,
                "unsourced": [n for s in letter.slots for n in s.unsourced_names],
                # The texts, so a person can read what the score does not grade.
                "texts": {s.name: s.text or s.proposed for s in letter.slots},
            }
        )
    return rows


def grade_letter(rows: list[Row]) -> dict[str, Any]:
    passed = sum(bool(row["passed"]) for row in rows)
    return {
        "score": round(passed / len(rows), 3) if rows else None,
        "detail": {
            "cases": f"{passed}/{len(rows)}",
            "refused_slots": sum(len(row.get("refused", [])) for row in rows),
            "names_to_check": sum(len(row.get("unsourced", [])) for row in rows),
        },
    }


SUITES: dict[str, Suite] = {
    "draft_letter": Suite(
        name="draft_letter",
        metric="lettres dont aucun emplacement n'est refusé ni vide",
        tier="writing",
        prompt_version=DRAFT_LETTER_TASK.prompt_version,
        threshold=None,
        run=run_letter,
        grade=grade_letter,
    ),
    "score_offer": Suite(
        name="score_offer",
        metric="corrélation de rang avec le classement fait à la main",
        tier="fast",
        prompt_version=SCORE_OFFER_TASK.prompt_version,
        threshold=SCORE_THRESHOLD,
        run=run_score,
        grade=grade_score,
    ),
    "extract_offer": Suite(
        name="extract_offer",
        metric="champs extraits correctement (contrat et télétravail à l'identique)",
        tier="fast",
        prompt_version=EXTRACT_OFFER_TASK.prompt_version,
        threshold=None,
        run=run_extract,
        grade=grade_extract,
    ),
    "select_cv_content": Suite(
        name="select_cv_content",
        metric="cas où toute la sélection attendue est retenue, et rien d'exclu",
        tier="writing",
        prompt_version=SELECT_CV_CONTENT_TASK.prompt_version,
        threshold=None,
        run=run_select_cv,
        grade=grade_select_cv,
    ),
}
