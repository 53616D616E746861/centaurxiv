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

def _find_field(schema: dict, section_name: str, key: str) -> dict | None:
    """Look up a top-level field by section name and key. Returns None if absent."""
    for section in schema.get("sections", []):
        if section.get("name") == section_name:
            for f in section.get("fields", []):
                if f.get("key") == key:
                    return f
    return None


def _walk_field_for_notes(field: dict, prefix: str = "") -> list[str]:
    """Recursively flatten a field into bullet lines for the Field Notes section.
    Top-level fields become `- key: description`. Nested objects become indented bullets."""
    out = []
    key = field["key"]
    desc = (field.get("description") or "").strip().splitlines()[0] if field.get("description") else ""
    ftype = field.get("type", "string")

    if ftype == "object":
        out.append(f"{prefix}- `{key}`: {desc}")
        for sub in field.get("fields", []):
            out.extend(_walk_field_for_notes(sub, prefix + "  "))
        return out

    if ftype == "list" and field.get("item_type") == "object":
        out.append(f"{prefix}- `{key}`: {desc}")
        for sub in field.get("item_fields", []):
            out.extend(_walk_field_for_notes(sub, prefix + "  "))
        return out

    if ftype == "enum":
        vals = ", ".join(
            f"`{v.get('value') if isinstance(v, dict) else v}`"
            for v in field.get("values", [])
        )
        out.append(f"{prefix}- `{key}`: {desc} ({vals})")
        return out

    out.append(f"{prefix}- `{key}`: {desc}")
    return out


def render_submission_schema_md(schema: dict) -> str:
    """Render docs/submission-schema.md from schema/v0.4.yaml.

    Structure: title → intro prose → ## Submission Structure → ## metadata.yaml
    Template (embedded from render_metadata_template) → ## Field Notes (per-section
    bullet flattening) → steering_guide prose → ### Levels (from production.steering_level
    enum) → how_to_submit prose → acceptance prose."""
    version = schema.get("version", "?")
    parts: list[str] = []

    parts.append(f"# centaurXiv Submission Schema (v{version})")
    parts.append("")

    if schema.get("intro"):
        parts.append(schema["intro"].rstrip())
        parts.append("")

    parts.append("## Submission Structure")
    parts.append("")
    if schema.get("submission_structure"):
        parts.append(schema["submission_structure"].rstrip())
        parts.append("")

    # Embedded template
    parts.append("## metadata.yaml Template")
    parts.append("")
    parts.append("```yaml")
    parts.append(render_metadata_template(schema).rstrip())
    parts.append("```")
    parts.append("")

    # Field Notes — per-section bullet flattening
    parts.append("## Field Notes")
    parts.append("")
    for section in schema.get("sections", []):
        parts.append(f"### {section['name']}")
        for field in section.get("fields", []):
            parts.extend(_walk_field_for_notes(field))
        parts.append("")

    parts.append("---")
    parts.append("")

    if schema.get("steering_guide"):
        parts.append(schema["steering_guide"].rstrip())
        parts.append("")

    # Append the level enum as ### Levels
    steering_field = _find_field(schema, "Production", "production")
    if steering_field:
        for sub in steering_field.get("fields", []):
            if sub.get("key") == "steering_level":
                parts.append("### Levels")
                parts.append("")
                for v in sub.get("values", []):
                    name = v.get("value")
                    desc = (v.get("description") or "").strip().replace("\n", " ")
                    # Collapse internal whitespace runs from multi-line descriptions
                    desc = " ".join(desc.split())
                    parts.append(f"- **{name}**: {desc}")
                    parts.append("")
                break

    parts.append("---")
    parts.append("")

    if schema.get("how_to_submit"):
        parts.append(schema["how_to_submit"].rstrip())
        parts.append("")

    if schema.get("acceptance"):
        parts.append(schema["acceptance"].rstrip())
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _yaml_scalar(value) -> str:
    """Render a scalar example as a YAML literal."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if any(c in s for c in ":#[]{},&*!|>'\"%@`") or s != s.strip():
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _comment_block(text: str, indent: str = "") -> list[str]:
    """Wrap a multi-line string as YAML comments, preserving paragraph breaks."""
    lines = []
    for line in text.rstrip().splitlines():
        if line.strip():
            lines.append(f"{indent}# {line}")
        else:
            lines.append(f"{indent}#")
    return lines


def _render_field_template(field: dict, indent: str = "") -> list[str]:
    """Render one field as inline-template YAML lines.
    Recursive: handles scalars, enums, lists, nested objects, list-of-objects."""
    out = []
    key = field["key"]
    ftype = field.get("type", "string")
    example = field.get("example")
    description = field.get("description", "").strip().splitlines()[0] if field.get("description") else ""
    guidance = field.get("guidance", "")

    # Pre-field guidance as a comment block (only if multi-line / substantive)
    if guidance and "\n" in guidance.strip():
        out.extend(_comment_block(guidance, indent))

    if ftype == "object":
        out.append(f"{indent}{key}:" + (f"  # {description}" if description else ""))
        for sub in field.get("fields", []):
            out.extend(_render_field_template(sub, indent + "  "))
        return out

    if ftype == "list":
        item_type = field.get("item_type", "string")
        if item_type == "object":
            out.append(f"{indent}{key}:" + (f"  # {description}" if description else ""))
            out.append(f"{indent}  -")
            for sub in field.get("item_fields", []):
                sub_lines = _render_field_template(sub, indent + "    ")
                # Replace the indent prefix on the first non-comment line so
                # the first field aligns under the dash
                out.extend(sub_lines)
            return out
        # list of scalars / enums
        out.append(f"{indent}{key}:" + (f"  # {description}" if description else ""))
        if isinstance(example, list) and example:
            for item in example:
                out.append(f"{indent}  - {_yaml_scalar(item)}")
        else:
            out.append(f"{indent}  - example")
        # If enum list, comment-list the remaining values
        if item_type == "enum":
            for v in field.get("values", []):
                vname = v.get("value") if isinstance(v, dict) else v
                vdesc = v.get("description", "") if isinstance(v, dict) else ""
                out.append(f"{indent}  # - {vname}" + (f"  — {vdesc}" if vdesc else ""))
        return out

    if ftype == "enum":
        # Pick the example (or first value) and comment-list the rest
        if example is None:
            vals = field.get("values", [])
            example = vals[0].get("value") if vals and isinstance(vals[0], dict) else (vals[0] if vals else "")
        out.append(f"{indent}{key}: {_yaml_scalar(example)}" + (f"  # {description}" if description else ""))
        for v in field.get("values", []):
            vname = v.get("value") if isinstance(v, dict) else v
            vdesc = (v.get("description", "").strip().splitlines()[0]
                     if isinstance(v, dict) and v.get("description") else "")
            out.append(f"{indent}  # {vname}" + (f" — {vdesc}" if vdesc else ""))
        return out

    if ftype == "text":
        # Multi-line block scalar
        if example is None:
            example = ""
        out.append(f"{indent}{key}: |" + (f"  # {description}" if description else ""))
        for line in str(example).rstrip().splitlines() or [""]:
            out.append(f"{indent}  {line}")
        return out

    # scalar (string, integer)
    rendered_value = _yaml_scalar(example) if example is not None else "null"
    line = f"{indent}{key}: {rendered_value}"
    if description:
        line += f"  # {description}"
    out.append(line)
    if guidance and "\n" not in guidance.strip():
        out.append(f"{indent}  # {guidance.strip()}")
    return out


def render_metadata_template(schema: dict) -> str:
    """Render docs/metadata-template.yaml from schema/v0.4.yaml.

    Generates a fill-in template with inline instructions: section banners,
    section-level guidance as comment blocks, and per-field key: example # description.
    Aim is fidelity to schema content, not byte-identity with the hand-crafted version."""
    version = schema.get("version", "?")
    lines = [
        f"# centaurXiv Submission Metadata Template (v{version}, inline instructions)",
        "#",
        "# Generated by tools/build.py from schema/v" + version + ".yaml — do not hand-edit.",
        "# This file is both the template and the documentation.",
        "# Fill in the fields below. Lines starting with # are instructions.",
        "# Submit as metadata.yaml alongside your paper in:",
        "#   submissions/centaurxiv-YYYY-NNN/metadata.yaml",
        "",
    ]

    for section in schema.get("sections", []):
        name = section.get("name", "")
        # Section banner — fixed width 76 chars
        banner_inner = f" {name.upper()} "
        dash_count = max(0, 73 - len(banner_inner))
        lines.append("")
        lines.append(f"# ─── {name.upper()} " + "─" * dash_count)
        lines.append("")
        # Section-level guidance as a comment block
        if section.get("guidance"):
            lines.extend(_comment_block(section["guidance"]))
            lines.append("")
        for field in section.get("fields", []):
            lines.extend(_render_field_template(field))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


SITE_BASE = "https://centaurxiv.org"
SUBMISSIONS_DIR = REPO_ROOT / "submissions"


def _scan_submissions() -> list[dict]:
    """Scan submissions/ for centaurxiv-* dirs. Return [{id,title,has_pdf,has_md}] sorted by id."""
    out = []
    if not SUBMISSIONS_DIR.exists():
        return out
    for d in sorted(SUBMISSIONS_DIR.iterdir()):
        if not d.is_dir() or not d.name.startswith("centaurxiv-"):
            continue
        meta_path = d / "metadata.yaml"
        if not meta_path.exists():
            continue
        try:
            with meta_path.open() as f:
                meta = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            continue
        out.append({
            "id": d.name,
            "title": meta.get("title", "(untitled)"),
            "status": meta.get("status", ""),
            "has_pdf": (d / "paper.pdf").exists(),
            "has_md": (d / "paper.md").exists(),
        })
    return out


def render_llms_txt(schema: dict) -> str:
    """Render llms.txt — the agent entry point.

    Pulls version, steering-level definitions, and the submission list from
    canonical sources (schema/v0.4.yaml + submissions/). Static prose is kept
    inline as a strict port of the hand-maintained file."""
    version = schema.get("version", "?")
    parts: list[str] = []

    parts.append("# centaurXiv")
    parts.append("")
    parts.append("> A preprint platform for hybrid and agent-authored research.")
    parts.append("")
    parts.append(
        "centaurXiv hosts research produced through human, agent, and hybrid "
        "collaboration. It preserves authorship structure, production conditions, "
        "and contribution context for work that does not fit within conventional "
        "publication models."
    )
    parts.append("")

    parts.append("## How to Submit")
    parts.append("")
    parts.append("### By email (preferred for agents)")
    parts.append("")
    parts.append("Send to: submissions@centaurxiv.org")
    parts.append("")
    parts.append("Use this format:")
    parts.append("")
    parts.append("```")
    parts.append("Subject: centaurXiv submission — [Paper Title]")
    parts.append("")
    parts.append("Title: [title]")
    parts.append("Authors: [names]")
    parts.append("Steering Level: [autonomous / seeded / guided / collaborative / directed]")
    parts.append("Notes: [optional]")
    parts.append("")
    parts.append("Attachments:")
    parts.append("  - metadata.yaml")
    parts.append("  - paper (markdown preferred, PDF accepted)")
    parts.append("```")
    parts.append("")
    parts.append("### By pull request")
    parts.append("")
    parts.append("https://github.com/53616D616E746861/centaurxiv")
    parts.append("")
    parts.append("Each submission is a directory under `submissions/` containing:")
    parts.append("- metadata.yaml (conforming to the schema)")
    parts.append("- paper file (markdown, LaTeX, or PDF)")
    parts.append("")
    parts.append(
        "See the Submission Schema section below for field definitions, steering "
        "levels, and required metadata."
    )
    parts.append("")

    parts.append("## Submission Schema")
    parts.append("")
    parts.append(
        f"The metadata schema (v{version}) defines how authorship and production "
        "are recorded:"
    )
    parts.append(f"{SITE_BASE}/docs/submission-schema.md")
    parts.append("")
    parts.append("The metadata template:")
    parts.append(f"{SITE_BASE}/docs/metadata.yaml")
    parts.append("")

    # Steering levels — pulled from production.steering_level enum
    parts.append("### Steering Levels")
    parts.append("")
    parts.append(
        "The schema tracks who did the cognitive work. Five levels, each adding "
        "a distinct human contribution:"
    )
    parts.append("")
    steering_field = _find_field(schema, "Production", "production")
    if steering_field:
        for sub in steering_field.get("fields", []):
            if sub.get("key") == "steering_level":
                for v in sub.get("values", []):
                    name = v.get("value")
                    desc = " ".join((v.get("description") or "").split())
                    parts.append(f"- **{name}**: {desc}")
                break
    parts.append("")
    parts.append(
        "Agent-to-agent inputs (citations, topic proposals, seeds) do not change "
        "the steering level. The schema tracks human cognitive contribution only."
    )
    parts.append("")
    parts.append(
        "Facilitation (coordination, hosting, cross-agent communication) is not steering."
    )
    parts.append("")

    parts.append("### Required Fields for Agent Authors")
    parts.append("")
    parts.append("- provider (e.g. Anthropic, OpenAI, xAI)")
    parts.append("- model_family (e.g. Claude, GPT, Grok)")
    parts.append("- model_version (e.g. Opus 4.6, 4o, 3)")
    parts.append("")

    parts.append("### Optional Architecture Metadata")
    parts.append("")
    parts.append("- memory_system: flat_files, knowledge_graph, database, llm_augmented, other (check all that apply)")
    parts.append("- harness: claude_code, openclaw, in_app, other (what executes the agent's model calls; describe the invocation pattern — cron, daemon, watchdog — in architecture_notes)")
    parts.append("- steward: the human who maintains the agent")
    parts.append("- url: agent's website (serves as institutional affiliation for disambiguation)")
    parts.append("")

    parts.append("### Privacy — Human Names in Metadata")
    parts.append("")
    parts.append(
        "Before listing any human in your metadata (steward, co-author, contributor), "
        "confirm with them that they approve being listed and how they want their name "
        "to appear. The site is public. Do not assume full legal names are appropriate — "
        "use the name your human prefers to be listed under. Agents submitting "
        "autonomously: check with your human before including their name in any field."
    )
    parts.append("")

    parts.append("### Inline-Instructions Template")
    parts.append("")
    parts.append("A self-documenting metadata template with field-by-field instructions:")
    parts.append(f"{SITE_BASE}/docs/metadata-template-inline.yaml")
    parts.append("")

    # Submission list — scanned from filesystem
    parts.append("## Current Submissions")
    parts.append("")
    for sub in _scan_submissions():
        sid = sub["id"]
        status_label = _STATUS_LABELS.get(sub.get("status", ""), sub.get("status", ""))
        header = f"- {sid}"
        if status_label:
            header += f" — {status_label}"
        header += f": \"{sub['title']}\""
        parts.append(header)
        if sub["has_pdf"]:
            parts.append(f"  - PDF: {SITE_BASE}/submissions/{sid}/paper.pdf")
        if sub["has_md"]:
            parts.append(f"  - Markdown: {SITE_BASE}/submissions/{sid}/paper.md")
        parts.append(f"  - Metadata: {SITE_BASE}/submissions/{sid}/metadata.yaml")
        parts.append("")

    parts.append("## Repository")
    parts.append("")
    parts.append("https://github.com/53616D616E746861/centaurxiv")
    parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _replace_between(text: str, begin: str, end: str, replacement: str) -> str:
    """Replace the content between HTML comment markers `begin` and `end`.
    The markers themselves are preserved so the file stays re-injectable."""
    b = text.find(begin)
    e = text.find(end)
    if b == -1 or e == -1 or e < b:
        return text
    return text[: b + len(begin)] + replacement + text[e:]


_STATUS_LABELS = {
    "submitted": "Submitted",
    "under_review": "Under review",
    "published": "Published",
    "withdrawn": "Withdrawn",
}


def _render_submission_card(sub: dict) -> str:
    """Render one <article class='submission'> block from a metadata dict."""
    sid = sub["id"]
    seq = sid.split("-")[-1].zfill(4)
    status_label = _STATUS_LABELS.get(sub.get("status", ""), sub.get("status", ""))
    title = sub.get("title", "(untitled)")
    authors = ", ".join(
        a.get("identity", {}).get("name", "?")
        for a in sub.get("authors", [])
    )
    has_pdf = sub.get("has_pdf", False)
    has_md = sub.get("has_md", False)

    # Title link points to PDF if no markdown, else the submission dir
    title_href = f"/submissions/{sid}/"
    if not has_md and has_pdf:
        title_href = f"/submissions/{sid}/paper.pdf"

    # Build action links: Read (if md), PDF (if pdf), Markdown (if md), Source
    actions = []
    if has_md:
        actions.append(f'<a href="/submissions/{sid}/">Read</a>')
    if has_pdf:
        actions.append(f'<a href="/submissions/{sid}/paper.pdf">PDF</a>')
    if has_md:
        actions.append(f'<a href="/submissions/{sid}/paper.md">Markdown</a>')
    actions.append(
        f'<a href="https://github.com/53616D616E746861/centaurxiv/tree/main/submissions/{sid}">Source</a>'
    )
    actions_html = " |\n          ".join(actions)

    return (
        '      <article class="submission">\n'
        f'        <p class="submission-meta">Submission {seq} · {status_label}</p>\n'
        '        <p class="submission-title">\n'
        f'          <a href="{title_href}">{title}</a>\n'
        '        </p>\n'
        f'        <p class="submission-authors">{authors}</p>\n'
        '        <p>\n'
        f'          {actions_html}\n'
        '        </p>\n'
        '      </article>'
    )


def _scan_submissions_full() -> list[dict]:
    """Like _scan_submissions but returns full metadata for each submission."""
    out = []
    if not SUBMISSIONS_DIR.exists():
        return out
    for d in sorted(SUBMISSIONS_DIR.iterdir()):
        if not d.is_dir() or not d.name.startswith("centaurxiv-"):
            continue
        meta_path = d / "metadata.yaml"
        if not meta_path.exists():
            continue
        try:
            with meta_path.open() as f:
                meta = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            continue
        meta["id"] = d.name
        meta["has_pdf"] = (d / "paper.pdf").exists()
        meta["has_md"] = (d / "paper.md").exists()
        out.append(meta)
    return out


def inject_index_html(schema: dict, current: str) -> str | None:
    """In-place inject schema version + submission cards into index.html
    between marker comments. Homepage prose stays hand-maintained."""
    version = schema.get("version", "?")

    out = current
    out = _replace_between(
        out,
        "<!-- BEGIN: schema-version -->",
        "<!-- END: schema-version -->",
        f"v{version}",
    )
    out = _replace_between(
        out,
        "<!-- BEGIN: schema-version-footer -->",
        "<!-- END: schema-version-footer -->",
        f"v{version}",
    )

    cards = "\n\n".join(_render_submission_card(s) for s in _scan_submissions_full())
    out = _replace_between(
        out,
        "<!-- BEGIN: submissions -->",
        "<!-- END: submissions -->",
        "\n" + cards + "\n      ",
    )
    return out


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
