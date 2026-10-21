"""Generate the public JSON schemas from the Pydantic models (A-09).

Usage:
    python tools/gen_schemas.py          # write src/neurogrid/schemas/*.schema.json
    python tools/gen_schemas.py --check  # fail if the committed schemas are outdated
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from neurogrid.config import Config
from neurogrid.kernel.provenance import Manifest
from neurogrid.kernel.rules import Rulepack
from neurogrid.model.results import Results, ScanResult

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "neurogrid" / "schemas"
MODELS: dict[str, type[BaseModel]] = {
    "results": Results,
    "scan": ScanResult,
    "config": Config,
    "rulepack": Rulepack,
    "manifest": Manifest,
}


def render(model: type[BaseModel]) -> str:
    schema = model.model_json_schema(mode="serialization")
    return json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outdated = []
    for name, model in MODELS.items():
        path = TARGET / f"{name}.schema.json"
        text = render(model)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                outdated.append(path.name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    if outdated:
        print("outdated schemas:", ", ".join(outdated), "- run python tools/gen_schemas.py")
        return 1
    print("schemas up to date" if args.check else f"wrote {len(MODELS)} schemas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
