"""The dependency rules are part of the product: they make the model's isolation structural."""

import logging
import re
from pathlib import Path

import grimp
from importlinter.cli import lint_imports

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "packages" / "core" / "src", ROOT / "apps" / "api" / "src"]
_WRITES_CV = re.compile(r"(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+cv_versions", re.I)


def test_import_contracts_hold():
    assert lint_imports() == 0
    # It configures logging, which disables every logger already created: later tests
    # checking what is logged would see nothing and pass for the wrong reason.
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            logger.disabled = False


def test_only_the_cv_routes_can_write_the_source_cv():
    """The CV is the user's own words and every model flow's source. Only the human
    editor may write it: a flow carrying model output must be structurally unable to."""
    graph = grimp.build_graph("jobingo", "jobingo_api")
    assert graph.find_modules_that_directly_import("jobingo.services.cv_editor") == {
        "jobingo_api.routes.cv"
    }

    writers = [
        path.name
        for root in SOURCES
        for path in root.rglob("*.py")
        if _WRITES_CV.search(path.read_text(encoding="utf-8"))
    ]
    assert writers == ["cv_editor.py"]


def test_the_model_is_only_reached_through_the_journal():
    """Services call `llm.journal.run_task`, which redacts, checks the budget and journals
    every call. Only the factory builds the real client, and only the client and the
    factory import the SDK."""
    graph = grimp.build_graph("jobingo", "jobingo_api", "anthropic")
    assert graph.find_modules_that_directly_import("jobingo.llm.anthropic_client") == {
        "jobingo.llm.factory"
    }
    sdk_importers = {
        module
        for module in graph.find_modules_that_directly_import("anthropic")
        if module.startswith("jobingo")
    }
    assert sdk_importers <= {"jobingo.llm.anthropic_client", "jobingo.llm.factory"}
