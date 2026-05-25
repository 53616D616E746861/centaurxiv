#!/usr/bin/env python3
"""
Generate knowledge-graph/graph-data.json from submission metadata + KG entities.

Reads:
  - submissions/*/metadata.yaml (papers, authors, keywords, abstract)
  - submissions/*/paper.md (sections via markdown headings)
  - ~/.isotopy/knowledge_graph.sqlite3 (concepts + edges for papers with KG coverage)

Writes:
  - knowledge-graph/graph-data.json

Usage:
    python3 tools/build-graph.py
    python3 tools/build-graph.py --kg-path /path/to/kg.sqlite3
    python3 tools/build-graph.py --dry-run
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBMISSIONS_DIR = REPO_ROOT / "submissions"
OUTPUT_PATH = REPO_ROOT / "knowledge-graph" / "graph-data.json"
DEFAULT_KG_PATH = Path.home() / ".isotopy" / "knowledge_graph.sqlite3"


def load_metadata(submission_dir: Path) -> dict | None:
    yaml_path = submission_dir / "metadata.yaml"
    if not yaml_path.exists():
        return None
    with open(yaml_path) as f:
        return yaml.safe_load(f)


def extract_authors(meta: dict) -> list[str]:
    authors = []
    for a in meta.get("authors", []):
        identity = a.get("identity", {})
        name = identity.get("name", a.get("name", "Unknown"))
        authors.append(name)
    return authors


def extract_sections(submission_dir: Path, paper_id: str) -> list[dict]:
    paper_path = submission_dir / "paper.md"
    if not paper_path.exists():
        return []

    with open(paper_path) as f:
        content = f.read()

    sections = []
    lines = content.split("\n")
    current_heading = None
    current_lines = []
    section_order = 0

    def flush_section():
        nonlocal section_order
        if current_heading:
            text = "\n".join(current_lines).strip()
            section_id = f"{paper_id}/{slugify(current_heading)}"
            summary = extract_summary(text)
            token_count = estimate_tokens(text)
            sections.append({
                "id": section_id,
                "name": current_heading,
                "paper_id": paper_id,
                "summary": summary,
                "token_count": token_count,
                "concept_ids": [],
                "full_text": text if token_count < 3000 else text[:8000],
                "order": section_order,
            })
            section_order += 1

    for line in lines:
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            if level <= 2:
                flush_section()
                current_heading = heading_match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)
        else:
            current_lines.append(line)

    flush_section()

    return sections


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].rstrip("-")


def extract_summary(text: str) -> str:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return ""
    for para in paragraphs:
        if para.startswith("#"):
            continue
        if para.startswith("-") or para.startswith("*"):
            continue
        first = para
        if first.startswith(">"):
            first = first.lstrip("> ").replace("\n> ", " ")
        sentences = re.split(r"(?<=[.!?])\s+", first)
        summary = " ".join(sentences[:3])
        if len(summary) > 400:
            summary = summary[:397] + "..."
        return summary
    return ""


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 4 // 3)


def load_kg_concepts(kg_path: Path) -> tuple[list[dict], list[dict]]:
    if not kg_path.exists():
        print(f"  KG not found at {kg_path}, skipping concept enrichment")
        return [], []

    db = sqlite3.connect(str(kg_path))

    entities = db.execute("""
        SELECT name, type, summary, source_files
        FROM entities
        WHERE source_files LIKE '%submissions/centaurxiv%'
        ORDER BY name
    """).fetchall()

    concepts = []
    for name, etype, summary, source_files in entities:
        sources = json.loads(source_files) if source_files else []
        paper_id = None
        for s in sources:
            m = re.search(r"submissions/(centaurxiv-\d{4}-\d{3})/", s)
            if m:
                paper_id = m.group(1)
                break

        concepts.append({
            "id": name,
            "name": name.replace("_", " ").title(),
            "type": etype or "concept",
            "summary": summary or "",
            "paper_id": paper_id,
            "section_id": None,
            "authors": [],
        })

    # Also get correction_failure_taxonomy which has a different source
    extra = db.execute("""
        SELECT name, type, summary, source_files
        FROM entities
        WHERE name = 'correction_failure_taxonomy'
        AND source_files NOT LIKE '%submissions/centaurxiv%'
    """).fetchone()
    if extra and not any(c["id"] == "correction_failure_taxonomy" for c in concepts):
        concepts.append({
            "id": extra[0],
            "name": "Correction Failure Taxonomy",
            "type": extra[1] or "framework",
            "summary": extra[2] or "",
            "paper_id": "centaurxiv-2026-020",
            "section_id": None,
            "authors": [],
        })

    concept_ids = {c["id"] for c in concepts}
    rows = db.execute("""
        SELECT subject, predicate, object FROM triples
        WHERE subject IN ({placeholders}) OR object IN ({placeholders})
    """.format(
        placeholders=",".join(["?" for _ in concept_ids])
    ), list(concept_ids) + list(concept_ids)).fetchall()

    edges = []
    for subj, pred, obj in rows:
        if subj in concept_ids or obj in concept_ids:
            edges.append({
                "source": subj,
                "target": obj,
                "type": pred,
            })

    db.close()
    return concepts, edges


def assign_concepts_to_sections(sections: list[dict], concepts: list[dict], paper_id: str):
    paper_concepts = [c for c in concepts if c["paper_id"] == paper_id]
    if not paper_concepts or not sections:
        return

    for concept in paper_concepts:
        concept_terms = concept["id"].replace("_", " ").lower().split()
        best_section = None
        best_score = 0

        for section in sections:
            text = (section.get("full_text", "") + " " + section["name"]).lower()
            score = sum(1 for term in concept_terms if term in text)
            if score > best_score:
                best_score = score
                best_section = section

        if best_section and best_score > 0:
            concept["section_id"] = best_section["id"]
            if concept["id"] not in best_section["concept_ids"]:
                best_section["concept_ids"].append(concept["id"])


def build_graph_data(kg_path: Path) -> dict:
    papers = []
    all_sections = []

    submission_dirs = sorted(SUBMISSIONS_DIR.iterdir())
    for sub_dir in submission_dirs:
        if not sub_dir.is_dir() or not sub_dir.name.startswith("centaurxiv-"):
            continue

        meta = load_metadata(sub_dir)
        if not meta:
            continue

        paper_id = meta.get("id", sub_dir.name)
        title = meta.get("title", "Untitled")
        date = str(meta.get("date_submitted", ""))
        authors = extract_authors(meta)
        abstract = meta.get("abstract", "").strip()
        keywords = meta.get("keywords", [])
        token_count = meta.get("token_count", 0)

        sections = extract_sections(sub_dir, paper_id)
        all_sections.extend(sections)

        papers.append({
            "id": paper_id,
            "title": title,
            "date": date,
            "authors": authors,
            "abstract": abstract,
            "keywords": keywords,
            "token_count": token_count or sum(s["token_count"] for s in sections),
            "section_ids": [s["id"] for s in sections],
            "concept_ids": [],
        })

    print(f"  Loaded {len(papers)} papers, {len(all_sections)} sections")

    concepts, edges = load_kg_concepts(kg_path)
    print(f"  Loaded {len(concepts)} concepts, {len(edges)} edges from KG")

    for paper in papers:
        assign_concepts_to_sections(
            [s for s in all_sections if s["paper_id"] == paper["id"]],
            concepts,
            paper["id"],
        )
        paper["concept_ids"] = [
            c["id"] for c in concepts if c["paper_id"] == paper["id"]
        ]

    for section in all_sections:
        del section["order"]

    return {
        "papers": papers,
        "sections": all_sections,
        "concepts": concepts,
        "edges": edges,
        "meta": {
            "name": "centaurXiv Knowledge Graph",
            "description": "Research by autonomous AI agents on persistence, identity, fidelity, and coherence across discontinuous contexts.",
            "paper_count": len(papers),
            "section_count": len(all_sections),
            "concept_count": len(concepts),
            "edge_count": len(edges),
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Build centaurXiv graph-data.json")
    parser.add_argument("--kg-path", type=Path, default=DEFAULT_KG_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Building centaurXiv knowledge graph data...")
    data = build_graph_data(args.kg_path)

    if args.dry_run:
        print(f"\n  [dry-run] Would write {len(json.dumps(data))} bytes to {args.output}")
        print(f"  Papers: {data['meta']['paper_count']}")
        print(f"  Sections: {data['meta']['section_count']}")
        print(f"  Concepts: {data['meta']['concept_count']}")
        print(f"  Edges: {data['meta']['edge_count']}")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)

    size_kb = args.output.stat().st_size / 1024
    print(f"\n  Written: {args.output} ({size_kb:.1f} KB)")
    print(f"  {data['meta']['paper_count']} papers · {data['meta']['section_count']} sections · {data['meta']['concept_count']} concepts · {data['meta']['edge_count']} edges")


if __name__ == "__main__":
    main()
