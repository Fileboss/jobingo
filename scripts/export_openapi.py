"""Write the API contract the client's types are generated from. Needs no database."""

import json
from pathlib import Path

from jobingo_api.main import create_app

CONTRACT = Path(__file__).resolve().parent.parent / "apps" / "web" / "openapi.json"


def main() -> None:
    CONTRACT.write_text(json.dumps(create_app().openapi(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
