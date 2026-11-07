"""`make eval`: run the labelled cases against the real API, with the eval key, and
record score, tokens, cost and latency per suite.

    uv run python -m evals.run                    # every suite
    uv run python -m evals.run --task select_cv_content
    uv run python -m evals.run --max-usd 2        # stop the run at this spend
    uv run python -m evals.run --compare select_cv_content

Answers are cached in `evals/.cache/`, so re-running unchanged prompts costs nothing.
Results go to `evals/results/<suite>.v<version>.<setup>.json`, committed: the
observability page reads them. Exit status: 1 when a suite with a threshold fails,
2 when the spending cap stopped the run.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from evals.harness import CachingClient, EvalBudgetExceededError, EvalConfig, Workspace
from evals.harness import anthropic_client as make_anthropic_client
from evals.suites import SUITES, Suite, load_cases
from jobingo.llm.anthropic_client import AnthropicLLMClient
from jobingo.llm.client import LLMClient

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def result_path(suite: Suite, config: EvalConfig, results_dir: Path = RESULTS_DIR) -> Path:
    return results_dir / f"{suite.name}.v{suite.prompt_version}.{config.setup(suite.tier)}.json"


def run_suite(
    suite: Suite,
    config: EvalConfig,
    client: CachingClient,
    *,
    results_dir: Path = RESULTS_DIR,
) -> dict[str, Any]:
    stopped = None
    rows: list[dict[str, Any]] = []
    with Workspace() as workspace:
        try:
            rows = suite.run(workspace, client, load_cases(suite.name))
        except EvalBudgetExceededError as exc:
            stopped = str(exc)

    graded: dict[str, Any] = (
        suite.grade(rows) if rows and not stopped else {"score": None, "detail": {}}
    )
    score: float | None = graded["score"]
    threshold = suite.threshold
    tiers = config.tiers()
    summary: dict[str, Any] = {
        "suite": suite.name,
        "metric": suite.metric,
        "prompt_version": suite.prompt_version,
        "setup": config.setup(suite.tier),
        "model": tiers[suite.tier].model,
        "thinking": tiers[suite.tier].thinking,
        "effort": tiers[suite.tier].effort,
        "score": score,
        "threshold": threshold,
        "passed": None if threshold is None or score is None else score >= threshold,
        "detail": graded["detail"],
        "cases": len(rows),
        "spend": client.spend.summary(),
        "stopped": stopped,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    path = result_path(suite, config, results_dir)
    if client.spend.live_calls == 0 and path.exists():
        # Re-graded from the cache, after a grader fix for instance: the answers are
        # the ones measured last time, so that run's spend and date stay. A free,
        # instant run would be a figure nobody measured.
        measured = json.loads(path.read_text(encoding="utf-8"))["summary"]
        summary["spend"] = measured["spend"]
        summary["run_at"] = measured["run_at"]
        summary["regraded_from_cache"] = True
    if stopped is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return summary


def _print(summary: dict[str, Any]) -> None:
    verdict = {True: "PASS", False: "FAIL", None: "info"}[summary["passed"]]
    spend = summary["spend"]
    print(f"\n{summary['suite']} v{summary['prompt_version']} ({summary['setup']}): {verdict}")
    print(f"  score: {summary['score']}  {summary['detail']}")
    print(
        f"  calls: {spend['live_calls']} live, {spend['cached_calls']} cached | "
        f"tokens: {spend['input_tokens']} in, {spend['output_tokens']} out | "
        f"cost: {spend['cost_usd']} $ | latency p50/p95: "
        f"{spend['latency_p50_ms']}/{spend['latency_p95_ms']} ms"
    )
    if summary.get("regraded_from_cache"):
        print("  re-graded from the cache: the spend above is the measured run's")
    if summary["stopped"]:
        print(f"  STOPPED: {summary['stopped']}")


def compare(name: str) -> int:
    files = sorted(RESULTS_DIR.glob(f"{name}.v*.json"))
    if not files:
        print(f"no results for {name}: run it first")
        return 1
    print(f"{name}: version.setup | score | cost $ | p50 ms | output tokens")
    for path in files:
        summary = json.loads(path.read_text(encoding="utf-8"))["summary"]
        spend = summary["spend"]
        print(
            f"  {path.stem.removeprefix(name + '.')} | {summary['score']} | {spend['cost_usd']}"
            f" | {spend['latency_p50_ms']} | {spend['output_tokens']}"
        )
    return 0


def main(argv: list[str] | None = None, live: LLMClient | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--task", choices=sorted(SUITES), help="run one suite only")
    parser.add_argument("--max-usd", type=Decimal, default=Decimal(1))
    parser.add_argument("--compare", metavar="SUITE", choices=sorted(SUITES))
    args = parser.parse_args(argv)
    if args.compare:
        return compare(args.compare)

    config = EvalConfig()
    inner: AnthropicLLMClient = make_anthropic_client(config)
    remaining: Decimal = args.max_usd
    exit_code = 0
    for name in [args.task] if args.task else list(SUITES):
        client = CachingClient(inner, remaining, live=live)
        summary = run_suite(SUITES[name], config, client)
        _print(summary)
        remaining -= client.spend.cost_usd
        if summary["passed"] is False:
            exit_code = 1
        if summary["stopped"]:
            return 2
    print(f"\nspent this run: {args.max_usd - remaining} $ (cap {args.max_usd} $)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
