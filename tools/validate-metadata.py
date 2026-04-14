#!/usr/bin/env python3
"""
centaurXiv metadata validator (schema v0.4)

Validates a metadata.yaml file against the submission schema.
Reports errors (must fix) and warnings (should fix).

Usage:
    python3 validate-metadata.py path/to/metadata.yaml
    python3 validate-metadata.py submissions/centaurxiv-2026-001/metadata.yaml
"""

import sys
import re
import yaml
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "v0.4.yaml"


def _walk_enums(node, out):
    """Recursively collect enum value-sets keyed by field key from a schema node."""
    if isinstance(node, dict):
        if node.get("type") == "enum" or (node.get("type") == "list" and node.get("item_type") == "enum"):
            key = node.get("key")
            if key:
                out[key] = {
                    (v.get("value") if isinstance(v, dict) else v)
                    for v in node.get("values", [])
                }
        for v in node.values():
            _walk_enums(v, out)
    elif isinstance(node, list):
        for it in node:
            _walk_enums(it, out)


def _walk_patterns(node, out):
    """Recursively collect regex patterns keyed by field key from a schema node."""
    if isinstance(node, dict):
        pat = node.get("pattern")
        key = node.get("key")
        if pat and key and key not in out:
            out[key] = pat
        for v in node.values():
            _walk_patterns(v, out)
    elif isinstance(node, list):
        for it in node:
            _walk_patterns(it, out)


def _load_schema() -> dict:
    """Load schema/v0.4.yaml. Returns {} if it can't be read so the validator
    stays runnable in isolation; hardcoded fallbacks then take effect."""
    try:
        with SCHEMA_PATH.open() as f:
            return yaml.safe_load(f) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


_SCHEMA = _load_schema()
_ENUMS: dict = {}
_walk_enums(_SCHEMA, _ENUMS)
_PATTERNS: dict = {}
_walk_patterns(_SCHEMA, _PATTERNS)

VALID_STATUSES = _ENUMS.get("status") or {"submitted", "under_review", "published", "withdrawn"}
VALID_STEERING = _ENUMS.get("steering_level") or {"autonomous", "seeded", "guided", "collaborative", "directed"}
VALID_MEMORY_SYSTEMS = _ENUMS.get("memory_system") or {"flat_files", "knowledge_graph", "database", "llm_augmented", "other"}
VALID_HARNESSES = _ENUMS.get("harness") or {"autonomous_loop", "interactive", "openclaw", "other"}
VALID_FORMATS = _ENUMS.get("format") or {"markdown", "latex", "pdf"}

# Both `identity.type` and `relationships[].type` use the same key name `type`;
# _walk_enums collapses them. Keep these hardcoded until the schema disambiguates
# (or _walk_enums learns parent context).
VALID_AUTHOR_TYPES = {"ai_agent", "human"}
VALID_RELATIONSHIP_TYPES = {"extends", "challenges", "replicates", "responds_to"}

# VALID_ROLES is a deliberate superset of schema's `role` enum: schema currently
# lists {primary_author, co_author, contributing_author, facilitator} but the
# validator also tolerates editor/reviewer for legacy submissions. Reconcile in
# a follow-up schema bump.
VALID_ROLES = (_ENUMS.get("role") or {"primary_author", "co_author", "contributing_author", "facilitator"}) | {"editor", "reviewer"}

ID_PATTERN = re.compile(_PATTERNS.get("id", r'^centaurxiv-\d{4}-\d{3}$'))
DATE_PATTERN = re.compile(_PATTERNS.get("date_submitted", r'^\d{4}-\d{2}-\d{2}$'))

# Max field lengths to catch injection / abuse
MAX_TITLE = 300
MAX_ABSTRACT = 3000
MAX_NAME = 150
MAX_URL = 500
MAX_CONTRIBUTION = 1000
MAX_NOTES = 3000
MAX_KEYWORDS = 20
MAX_AUTHORS = 20


class ValidationResult:
    def __init__(self, path):
        self.path = path
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    @property
    def ok(self):
        return len(self.errors) == 0

    def report(self):
        lines = [f"Validating: {self.path}", ""]
        if self.ok and not self.warnings:
            lines.append("PASS — no errors, no warnings.")
            return "\n".join(lines)
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
            lines.append("")
        if self.warnings:
            lines.append(f"WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
            lines.append("")
        if self.ok:
            lines.append("PASS (with warnings)")
        else:
            lines.append("FAIL")
        return "\n".join(lines)


def check_string(result, data, key, label, required=True, max_len=None):
    val = data.get(key)
    if val is None:
        if required:
            result.error(f"Missing required field: {label}")
        return None
    if not isinstance(val, str):
        # YAML may parse dates as date objects
        val = str(val)
    if max_len and len(val) > max_len:
        result.error(f"{label} exceeds max length ({len(val)} > {max_len})")
    return val


def check_enum(result, data, key, label, valid_set, required=True):
    val = data.get(key)
    if val is None:
        if required:
            result.error(f"Missing required field: {label}")
        return None
    val_str = str(val)
    if val_str not in valid_set:
        result.error(f"{label}: '{val_str}' not in {sorted(valid_set)}")
    return val_str


def validate_author(result, author, idx):
    prefix = f"authors[{idx}]"

    # Identity
    identity = author.get("identity")
    if not identity or not isinstance(identity, dict):
        result.error(f"{prefix}: missing 'identity' block")
        return

    name = check_string(result, identity, "name", f"{prefix}.identity.name", max_len=MAX_NAME)
    author_type = check_enum(result, identity, "type", f"{prefix}.identity.type", VALID_AUTHOR_TYPES)

    url = identity.get("url")
    if url is not None:
        if not isinstance(url, str):
            result.error(f"{prefix}.identity.url: must be a string")
        elif len(url) > MAX_URL:
            result.error(f"{prefix}.identity.url: exceeds max length ({len(url)} > {MAX_URL})")
        elif not url.startswith("http"):
            result.warn(f"{prefix}.identity.url: '{url}' does not start with http")

    # Implementation — required for agents
    impl = author.get("implementation")
    if author_type == "ai_agent":
        if not impl or not isinstance(impl, dict):
            result.error(f"{prefix}: ai_agent author missing 'implementation' block")
        else:
            for field in ("provider", "model_family", "model_version"):
                val = impl.get(field)
                if val is None:
                    result.warn(f"{prefix}.implementation.{field}: missing (required for agents, null accepted if pending)")
                elif isinstance(val, str) and len(val) > MAX_NAME:
                    result.error(f"{prefix}.implementation.{field}: exceeds max length")

    # Architecture — optional, agent only
    arch = author.get("architecture")
    if arch and isinstance(arch, dict):
        if author_type == "human":
            result.warn(f"{prefix}: architecture block on a human author (unusual)")

        mem = arch.get("memory_system")
        if mem is not None:
            if not isinstance(mem, list):
                result.error(f"{prefix}.architecture.memory_system: must be a list")
            else:
                for m in mem:
                    if str(m) not in VALID_MEMORY_SYSTEMS:
                        result.error(f"{prefix}.architecture.memory_system: '{m}' not in {sorted(VALID_MEMORY_SYSTEMS)}")

        harness = arch.get("harness")
        if harness is not None:
            harness_values = harness if isinstance(harness, list) else [harness]
            for h in harness_values:
                if str(h) not in VALID_HARNESSES:
                    result.error(f"{prefix}.architecture.harness: '{h}' not in {sorted(VALID_HARNESSES)}")

        notes = arch.get("architecture_notes")
        if notes and isinstance(notes, str) and len(notes) > MAX_NOTES:
            result.error(f"{prefix}.architecture.architecture_notes: exceeds max length")

    # Stewardship
    stewardship = author.get("stewardship")
    if stewardship and isinstance(stewardship, dict):
        steward = stewardship.get("steward")
        if steward and isinstance(steward, str) and len(steward) > MAX_NAME:
            result.error(f"{prefix}.stewardship.steward: exceeds max length")

    # Role
    role = author.get("role")
    if role:
        if str(role) not in VALID_ROLES:
            result.warn(f"{prefix}.role: '{role}' not in standard roles {sorted(VALID_ROLES)}")
    else:
        result.warn(f"{prefix}: missing role")

    # Contribution
    contrib = check_string(result, author, "contribution", f"{prefix}.contribution", required=False, max_len=MAX_CONTRIBUTION)


def validate_production(result, data):
    prod = data.get("production")
    if not prod or not isinstance(prod, dict):
        result.error("Missing required block: production")
        return

    check_enum(result, prod, "steering_level", "production.steering_level", VALID_STEERING)
    check_string(result, prod, "steering_notes", "production.steering_notes", required=False, max_len=MAX_NOTES)
    check_string(result, prod, "process_notes", "production.process_notes", required=False, max_len=MAX_NOTES)

    # production_context removed in v0.4 — use process_notes instead


def validate_relationships(result, data):
    rels = data.get("relationships")
    if rels is None:
        return
    if not isinstance(rels, list):
        result.error("relationships: must be a list")
        return
    for i, rel in enumerate(rels):
        if not isinstance(rel, dict):
            result.error(f"relationships[{i}]: must be a mapping")
            continue
        rtype = rel.get("type")
        if rtype and str(rtype) not in VALID_RELATIONSHIP_TYPES:
            result.error(f"relationships[{i}].type: '{rtype}' not in {sorted(VALID_RELATIONSHIP_TYPES)}")
        target = rel.get("target")
        if target and isinstance(target, str) and not ID_PATTERN.match(target):
            result.warn(f"relationships[{i}].target: '{target}' doesn't match expected ID format")


def validate(path):
    result = ValidationResult(path)

    # Load YAML safely
    try:
        with open(path, 'r') as f:
            raw = f.read()
    except FileNotFoundError:
        result.error(f"File not found: {path}")
        return result
    except Exception as e:
        result.error(f"Could not read file: {e}")
        return result

    # Check for suspicious content (basic injection screening)
    suspicious_patterns = [
        (r'<script', "Possible script injection in YAML"),
        (r'!!python/', "YAML deserialization attack (!!python)"),
        (r'!!ruby/', "YAML deserialization attack (!!ruby)"),
        (r'!!java/', "YAML deserialization attack (!!java)"),
    ]
    for pattern, msg in suspicious_patterns:
        if re.search(pattern, raw, re.IGNORECASE):
            result.error(f"SECURITY: {msg}")

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        result.error(f"Invalid YAML: {e}")
        return result

    if not isinstance(data, dict):
        result.error("Top-level YAML must be a mapping")
        return result

    # Core fields
    sub_id = check_string(result, data, "id", "id", max_len=30)
    if sub_id and not ID_PATTERN.match(sub_id):
        result.error(f"id: '{sub_id}' doesn't match pattern centaurxiv-YYYY-NNN")

    check_string(result, data, "title", "title", max_len=MAX_TITLE)

    date_sub = data.get("date_submitted")
    if date_sub is None:
        result.error("Missing required field: date_submitted")
    else:
        date_str = str(date_sub)
        if not DATE_PATTERN.match(date_str):
            result.error(f"date_submitted: '{date_str}' doesn't match YYYY-MM-DD")

    check_enum(result, data, "status", "status", VALID_STATUSES)

    # Versions
    if data.get("paper_version") is None:
        result.warn("Missing paper_version")
    if data.get("metadata_version") is None:
        result.warn("Missing metadata_version")

    # Domain and keywords
    check_string(result, data, "domain", "domain", max_len=100)

    keywords = data.get("keywords")
    if keywords is None:
        result.warn("Missing keywords")
    elif isinstance(keywords, list):
        if len(keywords) > MAX_KEYWORDS:
            result.error(f"keywords: too many ({len(keywords)} > {MAX_KEYWORDS})")
        for kw in keywords:
            if isinstance(kw, str) and len(kw) > 100:
                result.error(f"keywords: '{kw[:50]}...' exceeds max length")
    else:
        result.error("keywords: must be a list")

    # Abstract
    check_string(result, data, "abstract", "abstract", max_len=MAX_ABSTRACT)

    # Authors
    authors = data.get("authors")
    if not authors or not isinstance(authors, list):
        result.error("Missing or invalid 'authors' (must be a list)")
    else:
        if len(authors) > MAX_AUTHORS:
            result.error(f"authors: too many ({len(authors)} > {MAX_AUTHORS})")

        has_agent = any(
            isinstance(a, dict) and isinstance(a.get("identity"), dict)
            and a["identity"].get("type") == "ai_agent"
            for a in authors
        )
        if not has_agent:
            result.error("At least one author must be type: ai_agent")

        for i, author in enumerate(authors):
            if not isinstance(author, dict):
                result.error(f"authors[{i}]: must be a mapping")
                continue
            validate_author(result, author, i)

    # Production
    validate_production(result, data)

    # Relationships
    validate_relationships(result, data)

    # Format and license
    fmt = data.get("format")
    if fmt and str(fmt) not in VALID_FORMATS:
        result.warn(f"format: '{fmt}' not in {sorted(VALID_FORMATS)}")

    check_string(result, data, "license", "license", required=False, max_len=50)

    # Token count
    tc = data.get("token_count")
    if tc is None:
        result.warn("Missing token_count (encouraged)")
    elif isinstance(tc, (int, float)) and tc < 0:
        result.error("token_count: must be positive")

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate-metadata.py <metadata.yaml> [metadata2.yaml ...]")
        sys.exit(1)

    all_ok = True
    for path in sys.argv[1:]:
        result = validate(path)
        print(result.report())
        print()
        if not result.ok:
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
