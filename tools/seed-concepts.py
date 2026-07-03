#!/usr/bin/env python3
"""
Seed concept nodes for centaurXiv papers using OpenAI API.

Reads paper.md + metadata.yaml, extracts concepts via LLM,
writes them into knowledge-graph/concepts.json.

Usage:
    python3 tools/seed-concepts.py --paper 027
    python3 tools/seed-concepts.py --paper 027-028
    python3 tools/seed-concepts.py --paper 027 --dry-run
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBMISSIONS_DIR = REPO_ROOT / "submissions"
CONCEPTS_PATH = REPO_ROOT / "knowledge-graph" / "concepts.json"
CREDS_FILE = Path.home() / "autonomous-ai" / "isotopy-archive" / "credentials.txt"

CONCEPT_TYPES = [
    "concept", "finding", "mechanism", "failure_mode",
    "framework", "method", "instrument", "case_study",
]

PROMPT = """You are extracting concept nodes for a research paper knowledge graph. Each concept represents a distinct intellectual contribution: a term introduced, a finding established, a mechanism described, a framework proposed, or a method demonstrated.

Paper: {paper_title}
Paper ID: {paper_id}
Authors: {authors}
Date: {date}

Valid section IDs for this paper (use EXACTLY one of these for each concept's section_id):
{section_ids}

Full paper text:
{paper_text}

---

Extract concept nodes from this paper. For each concept, provide:
- id: short slug using paper number prefix (e.g., "027-residue", "028-four-register-framework")
- name: human-readable name
- type: one of {types}
- section_id: MUST be one of the valid section IDs listed above
- summary: 2-4 sentences describing what this concept IS and what work it does in the paper. Name specific claims, mechanisms, or distinctions. Use active voice. No meta-commentary.

Rules:
- Extract concepts that are INTRODUCED or DEVELOPED in this paper, not just mentioned
- For "type": use "concept" for terms/ideas, "finding" for empirical or analytical results, "mechanism" for how-something-works, "framework" for organizational structures, "method" for procedures/tests, "failure_mode" for failure patterns
- Summaries should be specific enough that an agent can decide whether to read the full section
- For a short paper (~2000 tokens), 4-7 concepts. For a long paper (~10000 tokens), 10-15 concepts
- Do NOT create concepts for the abstract, references, or metadata sections

Return ONLY a JSON array of concept objects. No other text."""


def load_openai_key():
    try:
        with open(CREDS_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENAI_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:80].rstrip("-")


def extract_section_ids(paper_text, paper_id):
    section_ids = []
    seen_first = False
    for line in paper_text.split("\n"):
        m = re.match(r"^(#{1,2})\s+(.+)$", line)
        if m and len(m.group(1)) <= 2:
            if not seen_first:
                seen_first = True
                continue
            heading = m.group(2).strip()
            section_ids.append(f"{paper_id}/{slugify(heading)}")
    return section_ids


def load_paper(paper_num):
    paper_id = f"centaurxiv-2026-{paper_num:03d}"
    sub_dir = SUBMISSIONS_DIR / paper_id

    paper_path = sub_dir / "paper.md"
    meta_path = sub_dir / "metadata.yaml"

    if not paper_path.exists():
        print(f"  Paper not found: {paper_path}")
        return None

    with open(paper_path) as f:
        paper_text = f.read()

    meta = {}
    if meta_path.exists():
        with open(meta_path) as f:
            meta = yaml.safe_load(f)

    title = meta.get("title", paper_id)
    date = str(meta.get("date_submitted", ""))
    authors = []
    for a in meta.get("authors", []):
        identity = a.get("identity", {})
        name = identity.get("name", a.get("name", "Unknown"))
        authors.append(name)

    section_ids = extract_section_ids(paper_text, paper_id)

    return {
        "paper_id": paper_id,
        "title": title,
        "date": date,
        "authors": authors,
        "text": paper_text,
        "section_ids": section_ids,
    }


def extract_concepts(paper, api_key, model="gpt-4o-mini"):
    import openai
    client = openai.OpenAI(api_key=api_key)

    text = paper["text"]
    if len(text) > 25000:
        text = text[:25000] + "\n[... truncated]"

    section_ids_str = "\n".join(f"  - {sid}" for sid in paper["section_ids"])

    prompt = PROMPT.format(
        paper_title=paper["title"],
        paper_id=paper["paper_id"],
        authors=", ".join(paper["authors"]),
        date=paper["date"],
        paper_text=text,
        section_ids=section_ids_str,
        types=", ".join(CONCEPT_TYPES),
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4000,
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content.strip()
    data = json.loads(content)

    if isinstance(data, dict):
        if "concepts" in data:
            return data["concepts"]
        return list(data.values())[0] if data else []
    return data


def main():
    parser = argparse.ArgumentParser(description="Seed concept nodes")
    parser.add_argument("--paper", type=str, required=True, help="Paper number(s): 027, 027-028")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    api_key = load_openai_key()
    if not api_key:
        print("Error: No OpenAI API key found")
        sys.exit(1)

    with open(CONCEPTS_PATH) as f:
        concepts_data = json.load(f)

    existing_ids = {c["id"] for c in concepts_data["concepts"]}

    if "-" in args.paper:
        start, end = args.paper.split("-", 1)
        paper_nums = list(range(int(start), int(end) + 1))
    else:
        paper_nums = [int(args.paper)]

    total_added = 0

    for num in paper_nums:
        paper = load_paper(num)
        if not paper:
            continue

        print(f"\n{'='*60}")
        print(f"Paper {num:03d}: {paper['title']}")
        print(f"  Authors: {', '.join(paper['authors'])}")
        print(f"  Text: {len(paper['text'])} chars")

        print(f"  Extracting concepts via {args.model}...")
        concepts = extract_concepts(paper, api_key, args.model)

        print(f"  Got {len(concepts)} concepts")

        for c in concepts:
            c["paper_id"] = paper["paper_id"]
            c["date"] = paper["date"]
            c["authors"] = paper["authors"]

            if "section_id" in c and c["section_id"] and not c["section_id"].startswith(paper["paper_id"]):
                c["section_id"] = f"{paper['paper_id']}/{c['section_id']}"

            if c["id"] in existing_ids:
                print(f"  [skip] {c['name']} (id {c['id']} exists)")
                continue

            if args.dry_run:
                print(f"  [would add] {c['name']} ({c['type']})")
                print(f"    section: {c.get('section_id', 'none')}")
                print(f"    summary: {c['summary'][:120]}...")
            else:
                concepts_data["concepts"].append(c)
                existing_ids.add(c["id"])
                print(f"  [added] {c['name']} ({c['type']})")

            total_added += 1

    if not args.dry_run and total_added > 0:
        with open(CONCEPTS_PATH, "w") as f:
            json.dump(concepts_data, f, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(concepts_data['concepts'])} total concepts to {CONCEPTS_PATH}")

    print(f"\nDone: {total_added} concepts {'would be ' if args.dry_run else ''}added")


if __name__ == "__main__":
    main()
