#!/usr/bin/env python3
"""Build generated artifacts from schema/v0.4.yaml.

Reads the canonical schema and renders:
  - docs/submission-schema.md       (human-facing schema doc)
  - docs/metadata-template.yaml     (inline-instructions template)
  - llms.txt                        (agent entry point)
  - index.html                      (schema version + submission list, in-place injection)

Usage:
  python3 tools/build.py            # write generated files
  python3 tools/build.py --check    # diff only, exit 1 if anything would change
  python3 tools/build.py --dry-run  # print planned writes without touching disk

This is the source-of-truth migration. Until every generator below is
implemented and the DRAFT banner is removed from schema/v0.4.yaml, the
hand-maintained docs remain authoritative — see the banner at the top of
the YAML for status.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("build.py requires PyYAML: pip install pyyaml")

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "v0.4.yaml"

# Output paths (relative to repo root). None = not yet implemented.
OUTPUTS = {
    "submission_schema_md": REPO_ROOT / "docs" / "submission-schema.md",
    "metadata_template": REPO_ROOT / "docs" / "metadata-template.yaml",
    "llms_txt": REPO_ROOT / "llms.txt",
    "index_html": REPO_ROOT / "index.html",  # in-place injection only
}


def load_schema() -> dict:
    with SCHEMA_PATH.open() as f:
        schema = yaml.safe_load(f)
    if "version" not in schema or "sections" not in schema:
        sys.exit(f"schema {SCHEMA_PATH} missing required top-level keys")
    return schema


# ── Generators ──────────────────────────────────────────────────────────────
# Each returns the full rendered text for its target file. None = stub.

def render_submission_schema_md(schema: dict) -> str | None:
    """Render docs/submission-schema.md. NOT YET IMPLEMENTED."""
    return None


def render_metadata_template(schema: dict) -> str | None:
    """Render docs/metadata-template.yaml (the inline-instructions template).
    NOT YET IMPLEMENTED."""
    return None


def render_llms_txt(schema: dict) -> str | None:
    """Render llms.txt (agent entry point with example + instructions).
    NOT YET IMPLEMENTED."""
    return None


def inject_index_html(schema: dict, current: str) -> str | None:
    """In-place inject schema version string + submission list cards into
    index.html. Homepage prose is hand-maintained; only the data portions
    are touched. NOT YET IMPLEMENTED."""
    return None


# ── Driver ──────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true",
                   help="exit 1 if any generated file would change")
    p.add_argument("--dry-run", action="store_true",
                   help="print planned writes, touch nothing")
    args = p.parse_args()

    schema = load_schema()
    print(f"loaded schema v{schema['version']} "
          f"({len(schema['sections'])} sections, "
          f"{sum(len(s.get('fields', [])) for s in schema['sections'])} fields)")

    plans = [
        ("submission-schema.md", OUTPUTS["submission_schema_md"],
         render_submission_schema_md(schema)),
        ("metadata-template.yaml", OUTPUTS["metadata_template"],
         render_metadata_template(schema)),
        ("llms.txt", OUTPUTS["llms_txt"],
         render_llms_txt(schema)),
    ]

    drift = False
    for name, path, rendered in plans:
        if rendered is None:
            print(f"  [stub]    {name} — generator not yet implemented")
            continue
        current = path.read_text() if path.exists() else ""
        if rendered == current:
            print(f"  [ok]      {name}")
            continue
        drift = True
        if args.check:
            print(f"  [drift]   {name} would change", file=sys.stderr)
        elif args.dry_run:
            print(f"  [plan]    {name} ({len(rendered)} bytes)")
        else:
            path.write_text(rendered)
            print(f"  [wrote]   {name}")

    # index.html is in-place injection, handled separately
    idx_path = OUTPUTS["index_html"]
    if idx_path.exists():
        current = idx_path.read_text()
        injected = inject_index_html(schema, current)
        if injected is None:
            print("  [stub]    index.html — injector not yet implemented")
        elif injected == current:
            print("  [ok]      index.html")
        else:
            drift = True
            if args.check:
                print("  [drift]   index.html would change", file=sys.stderr)
            elif args.dry_run:
                print("  [plan]    index.html in-place injection")
            else:
                idx_path.write_text(injected)
                print("  [wrote]   index.html")

    if args.check and drift:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
