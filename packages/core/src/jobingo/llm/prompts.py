"""The prompt templates, versioned files under `llm/prompts/`."""

from jinja2 import BaseLoader, Environment, PackageLoader, StrictUndefined


def prompt_environment(loader: BaseLoader) -> Environment:
    # StrictUndefined: renaming a payload field must fail loudly. With the default, the
    # prompt would render that section empty and the call would quietly degrade.
    # No HTML autoescape: prompts are text, and untrusted text goes through `xml`.
    env = Environment(  # nosec B701
        loader=loader, autoescape=False, undefined=StrictUndefined, keep_trailing_newline=True
    )
    env.filters["xml"] = escape_tags
    return env


def escape_tags(value: object) -> str:
    """Neutralise `<` and `>` in untrusted text, so that it cannot close a tag of the
    prompt (`</message>` followed by instructions). `&` stays as it is: the text stays
    readable and no entity is ever interpreted."""
    return str(value).replace("<", "&lt;").replace(">", "&gt;")


PROMPTS = prompt_environment(PackageLoader("jobingo.llm", "prompts"))
