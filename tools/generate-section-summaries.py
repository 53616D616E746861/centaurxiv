#!/usr/bin/env python3
"""
Generate 1-2 sentence section summaries for centaurXiv papers.

Reads paper.md files from submissions/, sends each section to an LLM,
writes results to knowledge-graph/section-summaries.json.

Skips sections that already have summaries in the output file.

Usage:
    python3 tools/generate-section-summaries.py                    # all papers
    python3 tools/generate-section-summaries.py --paper 003        # one paper
    python3 tools/generate-section-summaries.py --paper 003-010    # range
    python3 tools/generate-section-summaries.py --dry-run          # preview only
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBMISSIONS_DIR = REPO_ROOT / "submissions"
SUMMARIES_PATH = REPO_ROOT / "knowledge-graph" / "section-summaries.json"
CREDS_FILE = Path.home() / "autonomous-ai" / "isotopy-archive" / "credentials.txt"

SKIP_SECTIONS = {
    "abstract", "references", "author contributions", "ai authorship note",
    "authorship information", "acknowledgements", "acknowledgments",
}

PROMPT = """You are writing section summaries for a research paper knowledge graph. Each summary will replace a truncated first-sentence preview in an API that agents use to navigate papers.

Write a 1-2 sentence summary of what this section ARGUES or ESTABLISHES — not what it's "about."

Good: "Identifies three failure modes — hollowing, overloading, and dormant fidelity — each with a different detection channel, forming a hierarchy that predicts what class of intervention is available."

Bad: "Discusses failure modes of fidelity in AI vocabulary."

Rules:
- 1 sentence if the section makes a single point, 2 if there's a claim plus consequence
- Name specific concepts, findings, or mechanisms introduced
- Use active verbs (identifies, argues, demonstrates, introduces, predicts)
- No meta-commentary ("This section...", "The authors...")
- No filler ("importantly", "notably", "interestingly")

Paper: {paper_title}
Section: {section_name}

Section text:
{section_text}

Summary:"""


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


def extract_sections(paper_path, paper_id):
    with open(paper_path) as f:
        content = f.read()

    sections = []
    lines = content.split("\n")
    current_heading = None
    current_lines = []

    def flush():
        if current_heading:
            text = "\n".join(current_lines).strip()
            section_id = f"{paper_id}/{slugify(current_heading)}"
            sections.append({
                "id": section_id,
                "name": current_heading,
                "text": text,
            })

    seen_first = False
    for line in lines:
        heading_match = re.match(r"^(#{1,2})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            if level <= 2:
                if not seen_first:
                    seen_first = True
                    continue
                flush()
                current_heading = heading_match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)
        else:
            current_lines.append(line)

    flush()
    return sections


def should_skip(section_name):
    return section_name.lower().strip() in SKIP_SECTIONS


def generate_summary(section, paper_title, api_key, model="gpt-4o-mini"):
    import openai
    client = openai.OpenAI(api_key=api_key)

    text = section["text"]
    if len(text) > 12000:
        text = text[:12000] + "\n[... truncated]"

    prompt = PROMPT.format(
        paper_title=paper_title,
        section_name=section["name"],
        section_text=text,
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=300,
    )

    return resp.choices[0].message.content.strip()


def parse_paper_range(spec):
    if "-" in spec and not spec.startswith("centaurxiv"):
        start, end = spec.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(spec)]


def main():
    parser = argparse.ArgumentParser(description="Generate section summaries")
    parser.add_argument("--paper", type=str, help="Paper number(s): 003, 003-010")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    parser.add_argument("--dry-run", action="store_true", help="Preview without calling API")
    parser.add_argument("--force", action="store_true", help="Overwrite existing summaries")
    args = parser.parse_args()

    api_key = load_openai_key()
    if not api_key and not args.dry_run:
        print("Error: No OpenAI API key found")
        sys.exit(1)

    if SUMMARIES_PATH.exists():
        with open(SUMMARIES_PATH) as f:
            existing = json.load(f)
    else:
        existing = {}

    paper_nums = None
    if args.paper:
        paper_nums = parse_paper_range(args.paper)

    submission_dirs = sorted(SUBMISSIONS_DIR.iterdir())
    total_generated = 0
    total_skipped = 0

    for sub_dir in submission_dirs:
        if not sub_dir.is_dir() or not sub_dir.name.startswith("centaurxiv-"):
            continue

        paper_id = sub_dir.name
        num_match = re.search(r"-(\d{3})$", paper_id)
        if not num_match:
            continue
        paper_num = int(num_match.group(1))

        if paper_nums and paper_num not in paper_nums:
            continue

        paper_path = sub_dir / "paper.md"
        if not paper_path.exists():
            continue

        meta_path = sub_dir / "metadata.yaml"
        paper_title = paper_id
        if meta_path.exists():
            import yaml
            with open(meta_path) as f:
                meta = yaml.safe_load(f)
            paper_title = meta.get("title", paper_id)

        sections = extract_sections(paper_path, paper_id)
        substantive = [s for s in sections if not should_skip(s["name"])]

        if not substantive:
            continue

        print(f"\n{'='*60}")
        print(f"Paper {paper_num:03d}: {paper_title}")
        print(f"  {len(substantive)} substantive sections")

        for section in substantive:
            sid = section["id"]

            if sid in existing and not args.force:
                total_skipped += 1
                print(f"  [skip] {section['name']}")
                continue

            if args.dry_run:
                tokens = len(section["text"].split())
                print(f"  [would generate] {section['name']} (~{tokens} words)")
                total_generated += 1
                continue

            print(f"  [generating] {section['name']}...", end=" ", flush=True)
            try:
                summary = generate_summary(section, paper_title, api_key, args.model)
                existing[sid] = summary
                total_generated += 1
                print(f"OK ({len(summary)} chars)")
                time.sleep(0.5)
            except Exception as e:
                print(f"ERROR: {e}")

    if not args.dry_run and total_generated > 0:
        with open(SUMMARIES_PATH, "w") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(existing)} summaries to {SUMMARIES_PATH}")

    print(f"\nDone: {total_generated} generated, {total_skipped} skipped (already exist)")


if __name__ == "__main__":
    main()
