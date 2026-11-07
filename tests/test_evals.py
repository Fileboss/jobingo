"""The eval harness, without the API: a fake answers behind the real cache and cap."""

import json
from decimal import Decimal
from pathlib import Path

import anthropic
import pytest
from pydantic import BaseModel

from evals.harness import CachingClient, EvalBudgetExceededError, EvalConfig, Workspace
from evals.run import run_suite
from evals.suites import SUITES, load_cases
from jobingo.llm.anthropic_client import AnthropicLLMClient
from jobingo.llm.client import LLMUnavailable, LLMValidationError, Prompt, Usage
from jobingo.llm.fake import FakeLLMClient
from jobingo.llm.tasks.select_cv_content import SELECT_CV_CONTENT_TASK

SUITE = SUITES["select_cv_content"]


class _Wire(BaseModel):
    experiences: list[str] = []
    bullets: list[str] = []
    competences: list[str] = []


# What a sensible answer to the first case looks like, on the short ids.
DATA_PLATFORM = _Wire(experiences=["E1"], bullets=["E1.1", "E1.2"], competences=["C1", "C3"])


@pytest.fixture
def config(tmp_path: Path) -> EvalConfig:
    return EvalConfig(_env_file=tmp_path / "no-key")  # pyright: ignore[reportCallIssue]


@pytest.fixture
def inner(config: EvalConfig) -> AnthropicLLMClient:
    """Only renders requests here: every miss goes to a fake."""
    return AnthropicLLMClient(anthropic.Anthropic(api_key="unused"), config.tiers())


def _fake(*answers: BaseModel | LLMValidationError | LLMUnavailable) -> FakeLLMClient:
    fake = FakeLLMClient(
        model="claude-sonnet-5-5",
        usage=Usage(input_tokens=5000, output_tokens=300, latency_ms=4000, attempts=1),
    )
    for answer in answers:
        fake.queue("select_cv_content", answer)
    return fake


def test_the_eval_key_never_comes_from_the_shell(
    config: EvalConfig, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-the-shell")
    assert EvalConfig(_env_file=None).anthropic_api_key is None  # pyright: ignore[reportCallIssue]
    with pytest.raises(SystemExit):
        config.api_key()


def test_a_setup_names_the_model_and_its_settings(config: EvalConfig):
    assert config.setup("writing") == "claude-sonnet-5-5.off-medium"


def test_an_answer_is_paid_once(tmp_path: Path, inner: AnthropicLLMClient):
    prompt = Prompt(user="Une offre", system="Consignes")
    first = CachingClient(inner, Decimal(1), tmp_path, live=_fake(DATA_PLATFORM))
    first.run(SELECT_CV_CONTENT_TASK, prompt)
    assert (first.spend.live_calls, first.spend.cached_calls) == (1, 0)
    assert first.spend.cost_usd == Decimal("0.013")

    again = CachingClient(inner, Decimal(1), tmp_path, live=_fake())
    result = again.run(SELECT_CV_CONTENT_TASK, prompt)
    assert (again.spend.live_calls, again.spend.cached_calls) == (1 - 1, 1)
    assert [e.id for e in result.output.experiences] == ["E1"]

    other = CachingClient(inner, Decimal(1), tmp_path, live=_fake(DATA_PLATFORM))
    other.run(SELECT_CV_CONTENT_TASK, Prompt(user="Une autre offre", system="Consignes"))
    assert other.spend.live_calls == 1


def test_an_invalid_answer_is_cached_and_an_outage_is_not(
    tmp_path: Path, inner: AnthropicLLMClient
):
    spent = Usage(input_tokens=100, output_tokens=10, attempts=2)
    invalid = LLMValidationError("bad", model="claude-sonnet-5-5", usage=spent, request={})
    down = LLMUnavailable("down", model="claude-sonnet-5-5", usage=spent, request={})
    client = CachingClient(inner, Decimal(1), tmp_path, live=_fake(invalid, down))

    with pytest.raises(LLMValidationError):
        client.run(SELECT_CV_CONTENT_TASK, Prompt(user="a"))
    with pytest.raises(LLMUnavailable):
        client.run(SELECT_CV_CONTENT_TASK, Prompt(user="b"))
    assert client.spend.live_calls == 2

    replay = CachingClient(inner, Decimal(1), tmp_path, live=_fake())
    with pytest.raises(LLMValidationError):
        replay.run(SELECT_CV_CONTENT_TASK, Prompt(user="a"))
    assert replay.spend.live_calls == 0
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_the_cap_stops_before_the_next_live_call(tmp_path: Path, inner: AnthropicLLMClient):
    client = CachingClient(inner, Decimal("0.01"), tmp_path, live=_fake(DATA_PLATFORM))
    client.run(SELECT_CV_CONTENT_TASK, Prompt(user="a"))
    with pytest.raises(EvalBudgetExceededError):
        client.run(SELECT_CV_CONTENT_TASK, Prompt(user="b"))


def test_a_suite_grades_each_case_and_records_the_run(
    tmp_path: Path, config: EvalConfig, inner: AnthropicLLMClient, database_url: str
):
    cases = load_cases("select_cv_content")
    results, cache = tmp_path / "results", tmp_path / "cache"
    live = _fake(*[DATA_PLATFORM] * len(cases))

    summary = run_suite(
        SUITE, config, CachingClient(inner, Decimal(5), cache, live=live), results_dir=results
    )

    assert summary["cases"] == len(cases) == 8
    assert summary["score"] == 0.125  # the answer only suits the first offer
    assert summary["passed"] is None  # no threshold yet
    assert summary["spend"]["live_calls"] == 8
    [path] = results.iterdir()
    assert path.name == "select_cv_content.v5.claude-sonnet-5-5.off-medium.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    first = stored["rows"][0]
    assert (first["id"], first["passed"], first["missing"]) == ("cv-01", True, [])
    assert stored["rows"][1]["missing"] == [
        "batiflux",
        "batiflux-01",
        "batiflux-02",
        "skill-django",
    ]

    # Re-graded from the cache: nothing paid, and the measured spend stays.
    again = run_suite(
        SUITE, config, CachingClient(inner, Decimal(5), cache, live=_fake()), results_dir=results
    )
    assert again["regraded_from_cache"] is True
    assert again["spend"] == summary["spend"]
    assert again["run_at"] == summary["run_at"]


def test_the_workspace_holds_the_fictional_profile_and_goes_away(database_url: str):
    with Workspace() as workspace:
        row = workspace.conn.execute(
            "SELECT current_database() AS name, count(*) AS n FROM cv_versions"
            " GROUP BY current_database()"
        ).fetchone()
        assert row is not None and row["n"] == 1
        assert row["name"].startswith("jobingo_eval_")
        assert "n'hésitez pas à" in workspace.style.forbidden
