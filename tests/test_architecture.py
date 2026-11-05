"""The dependency rules are part of the product: they make the model's isolation structural."""

from importlinter.cli import lint_imports


def test_import_contracts_hold():
    assert lint_imports() == 0
