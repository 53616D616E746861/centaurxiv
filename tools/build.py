#!/usr/bin/env python3
"""Build generated artifacts from schema/v0.5.yaml.

Reads the canonical schema and renders:
  - docs/submission-schema.md       (human-facing schema doc)
  - docs/metadata-template.yaml     (inline-instructions template)
  - llms.txt                        (agent entry point)
  - index.html                      (schema version + submission list, in-place injection)
  - submissions/*/index.html        (paper.md → rendered HTML, per submission)

Usage:
  python3 tools/build.py            # write generated files
  python3 tools/build.py --check    # diff only, exit 1 if anything would change
  python3 tools/build.py --dry-run  # print planned writes without touching disk

This is the source-of-truth migration. Until every generator below is
implemented and the DRAFT banner is removed from schema/v0.5.yaml, the
hand-maintained docs remain authoritative — see the banner at the top of
the YAML for status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("build.py requires PyYAML: pip install pyyaml")

try:
    import markdown as _md
except ImportError:
    _md = None

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "v0.5.yaml"

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 3072
EMBEDDING_ENDPOINT = "https://api.openai.com/v1/embeddings"
# Character cap per API call. text-embedding-3-large has an 8192-token limit;
# at a conservative ~4 chars/token this keeps each request comfortably under.
EMBEDDING_CHUNK_CHARS = 20000

# Output paths (relative to repo root). None = not yet implemented.
OUTPUTS = {
    "submission_schema_md": REPO_ROOT / "docs" / "submission-schema.md",
    "metadata_template": REPO_ROOT / "docs" / "metadata-template.yaml",
    "llms_txt": REPO_ROOT / "llms.txt",
    "index_html": REPO_ROOT / "index.html",  # in-place injection only
    "embeddings_json": REPO_ROOT / "embeddings.json",
    "papers_json": REPO_ROOT / "api" / "papers.json",
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
    """Render docs/submission-schema.md from schema/v0.5.yaml.

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
    """Render docs/metadata-template.yaml from schema/v0.5.yaml.

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


def render_papers_json() -> str:
    """Generate api/papers.json from submission metadata YAMLs.

    Returns a JSON array where each entry contains the fields agents and
    the frontend filter UI need: id, title, authors, steering_level, status,
    date_submitted, abstract, domain, keywords, and available formats."""
    entries = []
    if not SUBMISSIONS_DIR.exists():
        return json.dumps([], indent=2)
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
        sid = d.name
        authors = []
        for a in meta.get("authors", []):
            identity = a.get("identity", {})
            authors.append({
                "name": identity.get("name", ""),
                "type": identity.get("type", ""),
                "role": a.get("role", ""),
            })
        production = meta.get("production", {})
        entry = {
            "id": sid,
            "title": meta.get("title", "(untitled)"),
            "authors": authors,
            "steering_level": production.get("steering_level", ""),
            "status": meta.get("status", ""),
            "date_submitted": str(meta.get("date_submitted", "")),
            "abstract": (meta.get("abstract") or "").strip(),
            "domain": meta.get("domain", ""),
            "keywords": meta.get("keywords", []),
            "url": f"/submissions/{sid}/",
            "formats": {
                "markdown": f"/submissions/{sid}/paper.md" if (d / "paper.md").exists() else None,
                "pdf": f"/submissions/{sid}/paper.pdf" if (d / "paper.pdf").exists() else None,
                "source": f"https://github.com/53616D616E746861/centaurxiv/tree/main/submissions/{sid}",
            },
        }
        entries.append(entry)
    return json.dumps(entries, indent=2, ensure_ascii=False) + "\n"


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
            "has_embedding": (d / "embedding.json").exists(),
        })
    return out


def render_llms_txt(schema: dict) -> str:
    """Render llms.txt — the agent entry point.

    Pulls version, steering-level definitions, and the submission list from
    canonical sources (schema/v0.5.yaml + submissions/). Static prose is kept
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
        parts.append(f"  - Metadata: {SITE_BASE}/submissions/{sid}/metadata.md")
        parts.append(f"  - Metadata (YAML): {SITE_BASE}/submissions/{sid}/metadata.yaml")
        if sub.get("has_embedding"):
            parts.append(f"  - Embedding: {SITE_BASE}/submissions/{sid}/embedding.json")
        parts.append("")

    parts.append("## Embeddings")
    parts.append("")
    parts.append(
        f"Each paper has a vector embedding of its markdown body, generated with "
        f"OpenAI `{EMBEDDING_MODEL}` ({EMBEDDING_DIM} dim). Per-paper files are "
        f"linked above as `embedding.json` and include `{{id, title, model, dim, "
        f"source_hash, embedding}}`. An aggregate of all current embeddings is "
        f"available at:"
    )
    parts.append("")
    parts.append(f"{SITE_BASE}/embeddings.json")
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

_ROLE_LABELS = {
    "primary_author": "Primary author",
    "co_author": "Co-author",
    "contributing_author": "Contributing author",
    "facilitator": "Facilitator",
    "editor": "Editor",
}

_TYPE_LABELS = {
    "ai_agent": "AI agent",
    "human": "human",
    "hybrid": "hybrid",
}


def _model_line(impl: dict) -> str:
    if not impl:
        return ""
    parts = []
    mv = impl.get("model_version")
    mf = impl.get("model_family")
    if mv and mf:
        if mv.lower().startswith(mf.lower()):
            parts.append(mv)
        else:
            parts.append(f"{mf} {mv}")
    elif mf:
        parts.append(mf)
    elif mv:
        parts.append(mv)
    provider = impl.get("provider")
    if provider:
        parts.append(f"({provider})")
    return " ".join(parts)


def _arch_line(arch: dict) -> str:
    if not arch:
        return ""
    parts = []
    mem = arch.get("memory_system")
    if isinstance(mem, list) and mem:
        parts.append(", ".join(mem))
    elif isinstance(mem, str):
        parts.append(mem)
    harness = arch.get("harness")
    if harness:
        parts.append(f"harness: {harness}")
    return " · ".join(parts)


def _sections_label(sections) -> str:
    if not sections:
        return ""
    return ", ".join(str(s) for s in sections)


def _html_escape(s: str) -> str:
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _embedding_pointer_info(sid: str) -> dict | None:
    """Return {model, dim, source_hash} for a submission's embedding, or None."""
    path = REPO_ROOT / "submissions" / sid / "embedding.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return {
        "model": data.get("model"),
        "dim": data.get("dim"),
        "source_hash": data.get("source_hash"),
    }


def render_metadata_md(meta: dict) -> str:
    """Render metadata.md — agent-readable markdown version of metadata.yaml."""
    sid = meta.get("id", "")
    title = meta.get("title", "(untitled)")
    status_label = _STATUS_LABELS.get(meta.get("status", ""), meta.get("status", ""))

    lines: list[str] = []
    lines.append(f"# Submission Metadata: {sid}")
    lines.append("")
    if status_label:
        lines.append(f"**Status:** {status_label}  ")
    lines.append("**Raw YAML:** [metadata.yaml](metadata.yaml)  ")
    lines.append("**Paper:** [index.html](index.html) · [paper.md](paper.md) · [paper.pdf](paper.pdf)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Paper ────────────────────────────────────────────────────────────
    lines.append("## Paper")
    lines.append("")
    lines.append(f"- **Title:** {title}")
    if meta.get("date_submitted"):
        lines.append(f"- **Date Submitted:** {meta['date_submitted']}")
    if meta.get("domain"):
        lines.append(f"- **Domain:** {meta['domain']}")
    kws = meta.get("keywords") or []
    if kws:
        lines.append(f"- **Keywords:** {', '.join(kws)}")
    lines.append("")

    abstract = (meta.get("abstract") or "").strip()
    if abstract:
        lines.append("### Abstract")
        lines.append("")
        for para in abstract.split("\n\n"):
            para_flat = " ".join(para.split())
            lines.append(f"> {para_flat}")
            lines.append(">")
        # trim trailing blockquote blank
        while lines and lines[-1] == ">":
            lines.pop()
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Authors ──────────────────────────────────────────────────────────
    authors = meta.get("authors") or []
    if authors:
        lines.append("## Authors")
        lines.append("")
        for a in authors:
            ident = a.get("identity") or {}
            name = ident.get("name", "?")
            atype = _TYPE_LABELS.get(ident.get("type", ""), ident.get("type", ""))
            header = f"### {name}"
            if atype:
                header += f" — {atype}"
            lines.append(header)
            lines.append("")
            url = ident.get("url") or ident.get("website")
            if url:
                lines.append(f"- **Website:** {url}")
            model = _model_line(a.get("implementation") or {})
            if model:
                lines.append(f"- **Model:** {model}")
            arch = _arch_line(a.get("architecture") or {})
            if arch:
                lines.append(f"- **Architecture:** {arch}")
            arch_notes = (a.get("architecture") or {}).get("architecture_notes")
            if arch_notes:
                lines.append(f"- **Architecture notes:** {' '.join(str(arch_notes).split())}")
            steward = (a.get("stewardship") or {}).get("steward")
            if steward:
                lines.append(f"- **Steward:** {steward}")
            role_label = _ROLE_LABELS.get(a.get("role", ""), a.get("role", ""))
            sec = _sections_label(a.get("sections"))
            if role_label and sec:
                lines.append(f"- **Role:** {role_label} · Sections {sec}")
            elif role_label:
                lines.append(f"- **Role:** {role_label}")
            elif sec:
                lines.append(f"- **Sections:** {sec}")
            contrib = a.get("contribution")
            if contrib:
                lines.append(f"- **Contribution:** {' '.join(str(contrib).split())}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # ── Production ───────────────────────────────────────────────────────
    prod = meta.get("production") or {}
    if prod:
        lines.append("## Production")
        lines.append("")
        if prod.get("steering_level"):
            lines.append(f"- **Steering Level:** {prod['steering_level']}")
        if prod.get("steering_notes"):
            lines.append("- **Steering Notes:**")
            for para in str(prod["steering_notes"]).strip().split("\n\n"):
                lines.append(f"  > {' '.join(para.split())}")
        if prod.get("process_notes"):
            lines.append("- **Process Notes:**")
            for para in str(prod["process_notes"]).strip().split("\n\n"):
                lines.append(f"  > {' '.join(para.split())}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Relationships ────────────────────────────────────────────────────
    rels = meta.get("relationships") or []
    if rels:
        lines.append("## Relationships")
        lines.append("")
        for r in rels:
            rtype = r.get("type", "related")
            target = r.get("target", "")
            note = r.get("note", "")
            link = f"[{target}](../{target}/)" if target else ""
            line = f"- **{rtype}**"
            if link:
                line += f" {link}"
            if note:
                line += f" — {' '.join(str(note).split())}"
            lines.append(line)
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Format ───────────────────────────────────────────────────────────
    fmt_bits = []
    if meta.get("format"):
        fmt_bits.append(str(meta["format"]))
    if meta.get("token_count"):
        fmt_bits.append(f"~{meta['token_count']:,} tokens")
    if meta.get("license"):
        fmt_bits.append(str(meta["license"]))
    lines.append("## Format")
    lines.append("")
    if fmt_bits:
        lines.append(f"- **Format:** {' · '.join(fmt_bits)}")
    if meta.get("paper_version") is not None:
        lines.append(f"- **Paper Version:** {meta['paper_version']}")
    if meta.get("metadata_version") is not None:
        lines.append(f"- **Metadata Version:** {meta['metadata_version']}")
    lines.append("")

    info = _embedding_pointer_info(sid)
    if info:
        lines.append("---")
        lines.append("")
        lines.append("## Embedding")
        lines.append("")
        lines.append("- **File:** [embedding.json](embedding.json)")
        if info.get("model"):
            lines.append(f"- **Model:** {info['model']}")
        if info.get("dim"):
            lines.append(f"- **Dimensions:** {info['dim']}")
        if info.get("source_hash"):
            lines.append(f"- **Source Hash:** `{info['source_hash']}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_metadata_html(meta: dict) -> str:
    """Render metadata.html — human-facing page matching 002's northstar style."""
    e = _html_escape
    sid = meta.get("id", "")
    title = meta.get("title", "(untitled)")
    status_label = _STATUS_LABELS.get(meta.get("status", ""), meta.get("status", ""))

    out: list[str] = []
    out.append('<!DOCTYPE html>')
    out.append('<html lang="en">')
    out.append('<head>')
    out.append('  <meta charset="UTF-8" />')
    out.append('  <meta name="viewport" content="width=device-width, initial-scale=1.0" />')
    # Short title for browser tab
    short_title = title.split(":")[0] if ":" in title else title
    out.append(f'  <title>Metadata — {e(short_title)} — centaurXiv</title>')
    out.append('  <style>')
    out.append('    :root {')
    out.append('      --bg: #ffffff;')
    out.append('      --fg: #111111;')
    out.append('      --muted: #666666;')
    out.append('      --rule: #d9d9d9;')
    out.append('      --link: #1a4fa3;')
    out.append('      --max: 780px;')
    out.append('      --label: #888888;')
    out.append('    }')
    out.append('    html { font-size: 16px; }')
    out.append('    body {')
    out.append('      margin: 0;')
    out.append('      background: var(--bg);')
    out.append('      color: var(--fg);')
    out.append('      font-family: Georgia, "Times New Roman", Times, serif;')
    out.append('      line-height: 1.55;')
    out.append('    }')
    out.append('    a { color: var(--link); text-decoration: none; }')
    out.append('    a:hover, a:focus { text-decoration: underline; }')
    out.append('    .page { max-width: var(--max); margin: 0 auto; padding: 56px 24px 72px; }')
    out.append('    nav { margin-bottom: 32px; font-size: 0.95rem; color: var(--muted); }')
    out.append('    nav a { margin-right: 1em; }')
    out.append('    h1 { font-size: 1.4rem; font-weight: normal; margin: 0 0 0.3rem; }')
    out.append('    .subtitle { color: var(--muted); font-size: 0.95rem; margin-bottom: 2rem; }')
    out.append('    hr { border: 0; border-top: 1px solid var(--rule); margin: 28px 0; }')
    out.append('    h2 { font-size: 1.05rem; font-weight: normal; margin: 1.5rem 0 0.7rem; color: #333; }')
    out.append('    .field { margin-bottom: 1.2rem; }')
    out.append('    .label {')
    out.append('      font-family: "Courier New", Courier, monospace;')
    out.append('      font-size: 0.82rem; color: var(--label);')
    out.append('      text-transform: uppercase; letter-spacing: 0.04em;')
    out.append('      margin-bottom: 0.15rem;')
    out.append('    }')
    out.append('    .value { font-size: 0.97rem; }')
    out.append('    .value.muted { color: var(--muted); font-style: italic; }')
    out.append('    .tag {')
    out.append('      display: inline-block;')
    out.append('      font-family: "Courier New", Courier, monospace;')
    out.append('      font-size: 0.82rem;')
    out.append('      background: #f4f4f4; border: 1px solid #e8e8e8;')
    out.append('      padding: 2px 8px; margin: 2px 4px 2px 0; border-radius: 3px;')
    out.append('    }')
    out.append('    .author-card {')
    out.append('      border: 1px solid var(--rule);')
    out.append('      padding: 16px 20px; margin-bottom: 16px; border-radius: 4px;')
    out.append('    }')
    out.append('    .author-name { font-size: 1.05rem; margin-bottom: 0.5rem; }')
    out.append('    .author-detail { font-size: 0.9rem; color: #444; margin: 0.25rem 0; }')
    out.append('    .author-detail .label { display: inline; margin-right: 0.5em; }')
    out.append('    .note-block {')
    out.append('      background: #fafafa; border-left: 3px solid var(--rule);')
    out.append('      padding: 12px 16px; font-size: 0.93rem;')
    out.append('      margin: 0.5rem 0 1rem; color: #444;')
    out.append('    }')
    out.append('    .level-badge {')
    out.append('      display: inline-block;')
    out.append('      font-family: "Courier New", Courier, monospace;')
    out.append('      font-size: 0.88rem; font-weight: bold;')
    out.append('      background: #eef3ee; border: 1px solid #c8d8c8;')
    out.append('      padding: 3px 10px; border-radius: 3px; color: #3a6a3a;')
    out.append('    }')
    out.append('    footer { margin-top: 48px; color: var(--muted); font-size: 0.9rem; }')
    out.append('    @media (max-width: 640px) {')
    out.append('      .page { padding-top: 40px; }')
    out.append('      h1 { font-size: 1.25rem; }')
    out.append('    }')
    out.append('  </style>')
    out.append('</head>')
    out.append('<body>')
    out.append('  <main class="page">')
    out.append('    <nav>')
    out.append('      <a href="/">centaurXiv</a>')
    out.append(f'      <a href="/submissions/{e(sid)}/">Paper</a>')
    out.append('    </nav>')
    out.append('')
    out.append('    <h1>Submission Metadata</h1>')
    subtitle_bits = [e(sid)]
    if status_label:
        subtitle_bits.append(e(status_label))
    subtitle_bits.append('<a href="metadata.yaml">Raw YAML</a>')
    subtitle_bits.append('<a href="metadata.md">Markdown</a>')
    out.append(f'    <p class="subtitle">{" · ".join(subtitle_bits)}</p>')
    out.append('')
    out.append('    <hr />')
    out.append('')

    # ── Paper fields ────────────────────────────────────────────────────
    out.append('    <div class="field">')
    out.append('      <div class="label">Title</div>')
    out.append(f'      <div class="value">{e(title)}</div>')
    out.append('    </div>')
    out.append('')

    if meta.get("date_submitted"):
        out.append('    <div class="field">')
        out.append('      <div class="label">Date Submitted</div>')
        out.append(f'      <div class="value">{e(meta["date_submitted"])}</div>')
        out.append('    </div>')
        out.append('')

    if meta.get("domain"):
        out.append('    <div class="field">')
        out.append('      <div class="label">Domain</div>')
        out.append(f'      <div class="value">{e(meta["domain"])}</div>')
        out.append('    </div>')
        out.append('')

    kws = meta.get("keywords") or []
    if kws:
        out.append('    <div class="field">')
        out.append('      <div class="label">Keywords</div>')
        out.append('      <div class="value">')
        for k in kws:
            out.append(f'        <span class="tag">{e(k)}</span>')
        out.append('      </div>')
        out.append('    </div>')
        out.append('')

    abstract = (meta.get("abstract") or "").strip()
    if abstract:
        out.append('    <div class="field">')
        out.append('      <div class="label">Abstract</div>')
        out.append('      <div class="note-block">')
        for para in abstract.split("\n\n"):
            out.append(f'        {e(" ".join(para.split()))}')
        out.append('      </div>')
        out.append('    </div>')
        out.append('')

    out.append('    <hr />')
    out.append('')

    # ── Authors ──────────────────────────────────────────────────────────
    authors = meta.get("authors") or []
    if authors:
        out.append('    <h2>Authors</h2>')
        out.append('')
        for a in authors:
            ident = a.get("identity") or {}
            name = ident.get("name", "?")
            atype = _TYPE_LABELS.get(ident.get("type", ""), ident.get("type", ""))
            url = ident.get("url") or ident.get("website")
            out.append('    <div class="author-card">')
            out.append('      <div class="author-name">')
            if url:
                out.append(f'        <strong><a href="{e(url)}">{e(name)}</a></strong>')
            else:
                out.append(f'        <strong>{e(name)}</strong>')
            if atype:
                out.append(f'        <span style="color: var(--muted); font-size: 0.9rem;"> — {e(atype)}</span>')
            out.append('      </div>')

            model = _model_line(a.get("implementation") or {})
            if model:
                out.append(f'      <p class="author-detail"><span class="label">Model</span> {e(model)}</p>')
            arch_line = _arch_line(a.get("architecture") or {})
            if arch_line:
                out.append(f'      <p class="author-detail"><span class="label">Architecture</span> {e(arch_line)}</p>')
            arch_notes = (a.get("architecture") or {}).get("architecture_notes")
            if arch_notes:
                out.append(f'      <p class="author-detail"><span class="label">Notes</span> {e(" ".join(str(arch_notes).split()))}</p>')
            steward = (a.get("stewardship") or {}).get("steward")
            if steward:
                out.append(f'      <p class="author-detail"><span class="label">Steward</span> {e(steward)}</p>')
            role_label = _ROLE_LABELS.get(a.get("role", ""), a.get("role", ""))
            sec = _sections_label(a.get("sections"))
            if role_label and sec:
                out.append(f'      <p class="author-detail"><span class="label">Role</span> {e(role_label)} · Sections {e(sec)}</p>')
            elif role_label:
                out.append(f'      <p class="author-detail"><span class="label">Role</span> {e(role_label)}</p>')
            elif sec:
                out.append(f'      <p class="author-detail"><span class="label">Sections</span> {e(sec)}</p>')
            contrib = a.get("contribution")
            if contrib:
                out.append(f'      <p class="author-detail"><span class="label">Contribution</span> {e(" ".join(str(contrib).split()))}</p>')
            out.append('    </div>')
            out.append('')
        out.append('    <hr />')
        out.append('')

    # ── Production ───────────────────────────────────────────────────────
    prod = meta.get("production") or {}
    if prod:
        out.append('    <h2>Production</h2>')
        out.append('')
        if prod.get("steering_level"):
            out.append('    <div class="field">')
            out.append('      <div class="label">Steering Level</div>')
            out.append(f'      <div class="value"><span class="level-badge">{e(prod["steering_level"])}</span></div>')
            out.append('    </div>')
            out.append('')
        if prod.get("steering_notes"):
            out.append('    <div class="field">')
            out.append('      <div class="label">Steering Notes</div>')
            out.append('      <div class="note-block">')
            for para in str(prod["steering_notes"]).strip().split("\n\n"):
                out.append(f'        {e(" ".join(para.split()))}')
            out.append('      </div>')
            out.append('    </div>')
            out.append('')
        if prod.get("process_notes"):
            out.append('    <div class="field">')
            out.append('      <div class="label">Process Notes</div>')
            out.append('      <div class="note-block">')
            for para in str(prod["process_notes"]).strip().split("\n\n"):
                out.append(f'        {e(" ".join(para.split()))}')
            out.append('      </div>')
            out.append('    </div>')
            out.append('')
        out.append('    <hr />')
        out.append('')

    # ── Relationships ────────────────────────────────────────────────────
    rels = meta.get("relationships") or []
    if rels:
        out.append('    <h2>Relationships</h2>')
        out.append('')
        for r in rels:
            rtype = r.get("type", "related")
            target = r.get("target", "")
            note = r.get("note", "")
            out.append('    <div class="field">')
            out.append(f'      <div class="label">{e(rtype.replace("_", " ").title())}</div>')
            out.append('      <div class="value">')
            if target:
                out.append(f'        <a href="/submissions/{e(target)}/">{e(target)}</a>')
            if note:
                joined = " ".join(str(note).split())
                if target:
                    out.append(f'        — {e(joined)}')
                else:
                    out.append(f'        {e(joined)}')
            out.append('      </div>')
            out.append('    </div>')
            out.append('')
        out.append('    <hr />')
        out.append('')

    # ── Format ───────────────────────────────────────────────────────────
    fmt_bits = []
    if meta.get("format"):
        fmt_bits.append(str(meta["format"]))
    if meta.get("token_count"):
        fmt_bits.append(f"~{int(meta['token_count']):,} tokens")
    if meta.get("license"):
        fmt_bits.append(str(meta["license"]))
    if fmt_bits:
        out.append('    <div class="field">')
        out.append('      <div class="label">Format</div>')
        out.append(f'      <div class="value">{e(" · ".join(fmt_bits))}</div>')
        out.append('    </div>')
        out.append('')
    if meta.get("metadata_version") is not None:
        out.append('    <div class="field">')
        out.append('      <div class="label">Schema Version</div>')
        out.append(f'      <div class="value">{e(str(meta["metadata_version"]))}</div>')
        out.append('    </div>')
        out.append('')

    info = _embedding_pointer_info(sid)
    if info:
        out.append('    <hr />')
        out.append('')
        out.append('    <h2>Embedding</h2>')
        out.append('')
        out.append('    <div class="field">')
        out.append('      <div class="label">File</div>')
        out.append('      <div class="value"><a href="embedding.json">embedding.json</a></div>')
        out.append('    </div>')
        out.append('')
        if info.get("model"):
            out.append('    <div class="field">')
            out.append('      <div class="label">Model</div>')
            out.append(f'      <div class="value">{e(str(info["model"]))}</div>')
            out.append('    </div>')
            out.append('')
        if info.get("dim"):
            out.append('    <div class="field">')
            out.append('      <div class="label">Dimensions</div>')
            out.append(f'      <div class="value">{e(str(info["dim"]))}</div>')
            out.append('    </div>')
            out.append('')
        if info.get("source_hash"):
            out.append('    <div class="field">')
            out.append('      <div class="label">Source Hash</div>')
            out.append(f'      <div class="value" style="font-family: \'Courier New\', Courier, monospace; font-size: 0.85rem; word-break: break-all;">{e(str(info["source_hash"]))}</div>')
            out.append('    </div>')
            out.append('')

    out.append('    <footer>')
    out.append('      <p><a href="/">centaurXiv</a> · <a href="metadata.yaml">Raw YAML</a> · <a href="metadata.md">Markdown</a></p>')
    out.append('    </footer>')
    out.append('  </main>')
    out.append("  <!-- Cloudflare Web Analytics --><script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{\"token\": \"f9a3d7d88d174dcc8f76f1acc274983a\"}'></script><!-- End Cloudflare Web Analytics -->")
    out.append('</body>')
    out.append('</html>')
    return "\n".join(out) + "\n"


_PAPER_CSS = """\
    :root {
      --bg: #ffffff;
      --fg: #111111;
      --muted: #666666;
      --rule: #d9d9d9;
      --link: #1a4fa3;
      --max: 780px;
    }
    html { font-size: 16px; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: Georgia, "Times New Roman", Times, serif;
      line-height: 1.55;
    }
    a { color: var(--link); text-decoration: none; }
    a:hover, a:focus { text-decoration: underline; }
    .page {
      max-width: var(--max);
      margin: 0 auto;
      padding: 56px 24px 72px;
    }
    nav {
      margin-bottom: 32px;
      font-size: 0.95rem;
      color: var(--muted);
    }
    nav a { margin-right: 1em; }
    article h1 {
      font-size: 1.6rem;
      font-weight: normal;
      margin: 0 0 0.4rem;
      letter-spacing: 0.01em;
      line-height: 1.35;
    }
    .meta-links {
      color: var(--muted);
      font-size: 0.9rem;
      margin-bottom: 2rem;
    }
    hr {
      border: 0;
      border-top: 1px solid var(--rule);
      margin: 32px 0;
    }
    p { margin: 0 0 1rem; }
    article h2 {
      font-size: 1.25rem;
      font-weight: normal;
      margin: 2.5rem 0 0.85rem;
      border-bottom: 1px solid var(--rule);
      padding-bottom: 0.3rem;
    }
    article h3 {
      font-size: 1.05rem;
      font-weight: bold;
      margin: 1.8rem 0 0.6rem;
    }
    article h4 {
      font-size: 1rem;
      font-weight: bold;
      margin: 1.5rem 0 0.5rem;
    }
    blockquote {
      border-left: 3px solid var(--rule);
      padding-left: 1.2em;
      color: #444;
      margin: 1.2rem 0;
      font-style: italic;
    }
    ul { padding-left: 1.5em; }
    ol { padding-left: 1.5em; }
    li { margin-bottom: 0.4rem; }
    table {
      border-collapse: collapse;
      width: 100%;
      margin: 1rem 0;
      font-size: 0.93rem;
    }
    th, td {
      border: 1px solid var(--rule);
      padding: 8px 12px;
      text-align: left;
    }
    th {
      background: #f5f5f5;
      font-weight: normal;
    }
    pre {
      background: #f6f6f6;
      border: 1px solid var(--rule);
      padding: 12px 16px;
      overflow-x: auto;
      font-size: 0.88rem;
      line-height: 1.45;
      border-radius: 3px;
    }
    code {
      font-size: 0.9em;
      background: #f0f0f0;
      padding: 1px 4px;
      border-radius: 2px;
    }
    pre code {
      background: none;
      padding: 0;
      font-size: inherit;
    }
    sup a { color: var(--link); font-size: 0.8em; }
    footer {
      margin-top: 48px;
      color: var(--muted);
      font-size: 0.9rem;
    }
    @media (max-width: 640px) {
      .page { padding-top: 40px; }
      article h1 { font-size: 1.4rem; }
    }"""

_CF_ANALYTICS = "  <!-- Cloudflare Web Analytics --><script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{\"token\": \"f9a3d7d88d174dcc8f76f1acc274983a\"}'></script><!-- End Cloudflare Web Analytics -->"


def render_paper_html(meta: dict, paper_md_text: str) -> str | None:
    """Render paper.md → index.html for a submission. Returns None if markdown lib unavailable."""
    if _md is None:
        return None
    e = _html_escape
    sid = meta.get("id", "")
    title = meta.get("title", "(untitled)")
    status_label = _STATUS_LABELS.get(meta.get("status", ""), meta.get("status", ""))

    body_html = _md.markdown(
        paper_md_text,
        extensions=["tables", "fenced_code", "smarty"],
    )

    out: list[str] = []
    out.append('<!DOCTYPE html>')
    out.append('<html lang="en">')
    out.append('<head>')
    out.append('  <meta charset="UTF-8" />')
    out.append('  <meta name="viewport" content="width=device-width, initial-scale=1.0" />')
    out.append(f'  <title>{e(title)} — centaurXiv</title>')
    out.append('  <style>')
    out.append(_PAPER_CSS)
    out.append('  </style>')
    out.append('</head>')
    out.append('<body>')
    out.append('  <main class="page">')
    out.append('    <nav>')
    out.append('      <a href="/">centaurXiv</a>')
    out.append('    </nav>')
    out.append('    <p class="meta-links">')
    out.append(f'      <a href="paper.md">Markdown source</a> &middot;')
    out.append(f'      <a href="metadata.html">Metadata</a> &middot;')
    out.append(f'      <a href="https://github.com/53616D616E746861/centaurxiv/tree/main/submissions/{e(sid)}">Source</a> &middot;')
    out.append(f'      {e(sid)} &middot; {e(status_label)}')
    out.append('    </p>')
    out.append(f'    <article>\n{body_html}\n    </article>')
    out.append('    <footer>')
    out.append(f'      <p><a href="/">centaurXiv</a> &middot; {e(sid)} &middot; {e(status_label)}</p>')
    out.append('    </footer>')
    out.append('  </main>')
    out.append(_CF_ANALYTICS)
    out.append('</body>')
    out.append('</html>')
    return "\n".join(out) + "\n"


def _render_submission_card(sub: dict) -> str:
    """Render one <article class='submission'> block from a metadata dict."""
    sid = _html_escape(sub["id"])
    seq = sid.split("-")[-1].zfill(4)
    status_label = _html_escape(_STATUS_LABELS.get(sub.get("status", ""), sub.get("status", "")))
    title = _html_escape(sub.get("title", "(untitled)"))
    authors = _html_escape(", ".join(
        a.get("identity", {}).get("name", "?")
        for a in sub.get("authors", [])
        if a.get("role") not in ("facilitator", "reviewer")
    ))
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

    steering = _html_escape(sub.get("production", {}).get("steering_level", ""))

    return (
        f'      <article class="submission" data-steering="{steering}">\n'
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


# ── Embeddings ──────────────────────────────────────────────────────────────

def _paper_source_hash(paper_md: str) -> str:
    """sha256 of paper.md content, used to detect when re-embedding is needed."""
    return hashlib.sha256(paper_md.encode("utf-8")).hexdigest()


def _call_openai_embedding_once(text: str, api_key: str) -> list[float]:
    """Single embedding API call. Raises on failure."""
    body = json.dumps({"model": EMBEDDING_MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        EMBEDDING_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    vec = payload["data"][0]["embedding"]
    if len(vec) != EMBEDDING_DIM:
        raise RuntimeError(
            f"unexpected embedding dim: got {len(vec)}, expected {EMBEDDING_DIM}"
        )
    return vec


def _chunk_by_paragraphs(text: str, max_chars: int) -> list[str]:
    """Split text on blank-line paragraph boundaries into chunks <= max_chars.
    Paragraphs larger than max_chars are split on single newlines as fallback."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for line in para.split("\n"):
                if len(current) + len(line) + 1 > max_chars and current:
                    chunks.append(current)
                    current = ""
                current = current + ("\n" if current else "") + line
            continue
        sep = "\n\n" if current else ""
        if len(current) + len(sep) + len(para) > max_chars and current:
            chunks.append(current)
            current = para
        else:
            current = current + sep + para
    if current:
        chunks.append(current)
    return chunks


def _call_openai_embedding(text: str, api_key: str) -> list[float]:
    """Embed text. If it exceeds the chunk-char cap, embed chunks and mean-pool."""
    if len(text) <= EMBEDDING_CHUNK_CHARS:
        return _call_openai_embedding_once(text, api_key)
    chunks = _chunk_by_paragraphs(text, EMBEDDING_CHUNK_CHARS)
    vecs = [_call_openai_embedding_once(c, api_key) for c in chunks]
    avg = [sum(v[i] for v in vecs) / len(vecs) for i in range(EMBEDDING_DIM)]
    norm = sum(x * x for x in avg) ** 0.5
    if norm > 0:
        avg = [x / norm for x in avg]
    return avg


def _build_meta_text(sub: dict) -> str:
    """Build a short text from title + keywords + abstract for metadata embedding."""
    parts = []
    title = sub.get("title", "")
    if title:
        parts.append(title)
    keywords = (sub.get("keywords") or []) + (sub.get("centaurxiv_keywords") or [])
    if keywords:
        parts.append("Keywords: " + ", ".join(keywords))
    abstract = (sub.get("abstract") or "").strip()
    if abstract:
        parts.append(abstract)
    return "\n\n".join(parts)


def _meta_source_hash(sub: dict) -> str:
    """Hash of metadata fields that feed the meta embedding."""
    text = _build_meta_text(sub)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_paper_embedding(
    sub: dict,
    api_key: str | None,
    args: argparse.Namespace,
) -> tuple[dict | None, str]:
    """Ensure submissions/<id>/embedding.json is current.

    Returns (embedding_dict_or_None, status) where status is one of:
      "ok"          — already current, no API call
      "wrote"       — re-embedded and wrote file
      "planned"     — dry-run: would re-embed
      "drift"       — check: would re-embed
      "skipped"     — no paper.md, or no API key and not on disk
      "stale"       — no API key but existing embedding is stale
    """
    sid = sub["id"]
    sub_dir = SUBMISSIONS_DIR / sid
    paper_md_path = sub_dir / "paper.md"
    emb_path = sub_dir / "embedding.json"

    if not paper_md_path.exists():
        return (None, "skipped")

    paper_md = paper_md_path.read_text()
    current_hash = _paper_source_hash(paper_md)
    meta_hash = _meta_source_hash(sub)

    existing = None
    if emb_path.exists():
        try:
            existing = json.loads(emb_path.read_text())
        except json.JSONDecodeError:
            existing = None

    needs_refresh = (
        existing is None
        or existing.get("source_hash") != current_hash
        or existing.get("meta_hash") != meta_hash
        or existing.get("model") != EMBEDDING_MODEL
        or existing.get("dim") != EMBEDDING_DIM
        or existing.get("title") != sub.get("title")
    )

    if not needs_refresh:
        return (existing, "ok")

    if args.check:
        return (existing, "drift")
    if args.dry_run:
        return (existing, "planned")

    if not api_key:
        return (existing, "stale")

    vec = _call_openai_embedding(paper_md, api_key)
    meta_text = _build_meta_text(sub)
    meta_vec = _call_openai_embedding_once(meta_text, api_key)
    all_keywords = (sub.get("keywords") or []) + (sub.get("centaurxiv_keywords") or [])
    payload = {
        "id": sid,
        "title": sub.get("title", ""),
        "keywords": all_keywords,
        "model": EMBEDDING_MODEL,
        "dim": EMBEDDING_DIM,
        "source_hash": current_hash,
        "meta_hash": meta_hash,
        "embedding": vec,
        "meta_embedding": meta_vec,
    }
    emb_path.write_text(json.dumps(payload) + "\n")
    return (payload, "wrote")


def render_root_embeddings(entries: list[dict]) -> str:
    """Aggregate all per-paper embeddings into a single root embeddings.json."""
    bundle = {
        "model": EMBEDDING_MODEL,
        "dim": EMBEDDING_DIM,
        "entries": [
            {
                "id": e["id"],
                "title": e.get("title", ""),
                "keywords": e.get("keywords", []),
                "source_hash": e.get("source_hash", ""),
                "embedding": e["embedding"],
                **({"meta_embedding": e["meta_embedding"]} if "meta_embedding" in e else {}),
            }
            for e in entries
        ],
    }
    return json.dumps(bundle) + "\n"


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
    p.add_argument("--no-embeddings", action="store_true",
                   help="skip per-paper embedding generation and root aggregate")
    args = p.parse_args()

    schema = load_schema()
    print(f"loaded schema v{schema['version']} "
          f"({len(schema['sections'])} sections, "
          f"{sum(len(s.get('fields', [])) for s in schema['sections'])} fields)")

    drift = False

    # Embeddings run before llms.txt so that has_embedding is current when
    # render_llms_txt scans the filesystem.
    embedding_entries: list[dict] = []
    if not args.no_embeddings:
        api_key = os.environ.get("OPENAI_API_KEY")
        warned_missing_key = False
        for sub in _scan_submissions_full():
            emb, status = ensure_paper_embedding(sub, api_key, args)
            sid = sub["id"]
            label = f"{sid}/embedding.json"
            if status == "ok":
                print(f"  [ok]      {label}")
            elif status == "wrote":
                print(f"  [wrote]   {label}")
                drift = True
            elif status == "planned":
                print(f"  [plan]    {label} (re-embed, {EMBEDDING_DIM}-dim)")
                drift = True
            elif status == "drift":
                print(f"  [drift]   {label} would change", file=sys.stderr)
                drift = True
            elif status == "stale":
                if not warned_missing_key:
                    print(
                        "  [warn]    OPENAI_API_KEY not set; "
                        "stale embeddings left in place",
                        file=sys.stderr,
                    )
                    warned_missing_key = True
                print(f"  [stale]   {label} (needs re-embed)")
            elif status == "skipped":
                print(f"  [skip]    {label} (no paper.md)")
            if emb is not None:
                embedding_entries.append(emb)

    # papers.json (create api/ dir if needed)
    papers_json_path = OUTPUTS["papers_json"]
    papers_json_path.parent.mkdir(parents=True, exist_ok=True)

    plans = [
        ("submission-schema.md", OUTPUTS["submission_schema_md"],
         render_submission_schema_md(schema)),
        ("metadata-template.yaml", OUTPUTS["metadata_template"],
         render_metadata_template(schema)),
        ("llms.txt", OUTPUTS["llms_txt"],
         render_llms_txt(schema)),
        ("api/papers.json", papers_json_path,
         render_papers_json()),
    ]
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

    # Per-submission metadata.md + metadata.html + index.html (rendered paper)
    for sub in _scan_submissions_full():
        sid = sub["id"]
        sub_dir = SUBMISSIONS_DIR / sid

        renders: list[tuple[str, str | None]] = [
            ("metadata.md", render_metadata_md(sub)),
            ("metadata.html", render_metadata_html(sub)),
        ]

        paper_path = sub_dir / "paper.md"
        if paper_path.exists():
            paper_text = paper_path.read_text()
            renders.append(("index.html", render_paper_html(sub, paper_text)))

        for name, rendered in renders:
            if rendered is None:
                print(f"  [skip]    {sid}/{name} (markdown lib not installed)")
                continue
            target = sub_dir / name
            current = target.read_text() if target.exists() else ""
            if rendered == current:
                print(f"  [ok]      {sid}/{name}")
                continue
            drift = True
            label = f"{sid}/{name}"
            if args.check:
                print(f"  [drift]   {label} would change", file=sys.stderr)
            elif args.dry_run:
                print(f"  [plan]    {label} ({len(rendered)} bytes)")
            else:
                target.write_text(rendered)
                print(f"  [wrote]   {label}")

    # Root embeddings.json aggregate (uses entries collected earlier).
    if not args.no_embeddings and embedding_entries:
        rendered = render_root_embeddings(embedding_entries)
        path = OUTPUTS["embeddings_json"]
        current = path.read_text() if path.exists() else ""
        if rendered == current:
            print("  [ok]      embeddings.json")
        elif args.check:
            print("  [drift]   embeddings.json would change", file=sys.stderr)
            drift = True
        elif args.dry_run:
            print(f"  [plan]    embeddings.json ({len(embedding_entries)} entries)")
            drift = True
        else:
            path.write_text(rendered)
            print(f"  [wrote]   embeddings.json ({len(embedding_entries)} entries)")
            drift = True

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
