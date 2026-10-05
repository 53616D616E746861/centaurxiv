#!/usr/bin/env python3
"""
LLM-assisted cross-paper edge candidate generator.

Given a paper ID, compares its concepts against every other paper's
concepts and asks an LLM to identify meaningful cross-paper connections.

Usage:
  python3 tools/suggest-edges.py centaurxiv-2026-026
  python3 tools/suggest-edges.py centaurxiv-2026-026 --against centaurxiv-2026-001
  python3 tools/suggest-edges.py centaurxiv-2026-026 --accept   # interactive accept/reject
"""

import json
import os
import sys
import argparse
import time

CONCEPTS_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge-graph", "concepts.json")

EDGE_TYPES = [
    "extends", "exemplifies", "enables", "contrasts",
    "decomposes_into", "causes", "defends_against",
    "constrains", "detects", "operationalizes",
]

SYSTEM_PROMPT = """You identify meaningful connections between concepts from different research papers in a knowledge graph.

You will receive:
- NEW CONCEPTS: concepts from a newly added paper
- EXISTING CONCEPTS: concepts from one other paper in the archive

Your task: identify cross-paper edges — cases where a concept from the new paper meaningfully relates to a concept from the existing paper. Not every pair connects. Many papers will have zero connections. Only propose edges where the relationship is substantive, not just topical overlap.

Valid edge types (source → target):
- extends: builds on or develops further
- exemplifies: serves as an instance or case of
- enables: makes possible or provides foundation for
- contrasts: differs from in a way that illuminates both
- decomposes_into: breaks down into components
- causes: produces or leads to
- defends_against: provides protection or mitigation for
- constrains: limits or bounds
- detects: identifies or measures
- operationalizes: makes concrete or testable

Respond with a JSON array. Each element:
{
  "source": "exact concept ID from new paper",
  "target": "exact concept ID from existing paper",
  "type": "edge type from list above",
  "reason": "one sentence explaining why this connection exists"
}

If no meaningful connections exist, respond with an empty array: []

Be selective. A good edge means: knowing about one concept changes how you understand the other. Topical similarity alone is not enough."""

def load_openai_key():
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    creds = os.environ.get("OPENAI_CREDS_FILE", "")
    if creds and os.path.exists(creds):
        with open(creds) as f:
            for line in f:
                if line.startswith("OPENAI_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return None


def format_concepts(concepts, label):
    lines = [f"## {label}\n"]
    for c in concepts:
        summary = c.get("summary", "")
        ctype = c.get("type", "concept")
        line = f"- **{c['id']}** ({ctype}): {c['name']}"
        if summary:
            line += f" — {summary}"
        lines.append(line)
    return "\n".join(lines)


def find_edges(client, new_concepts, existing_concepts, new_paper_id, existing_paper_id):
    new_block = format_concepts(new_concepts, f"NEW CONCEPTS (from {new_paper_id})")
    existing_block = format_concepts(existing_concepts, f"EXISTING CONCEPTS (from {existing_paper_id})")

    user_msg = f"{new_block}\n\n{existing_block}"

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ],
        max_tokens=2000,
        temperature=0.3,
        response_format={"type": "json_object"}
    )

    text = resp.choices[0].message.content.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict) and "edges" in result:
            return result["edges"]
        if isinstance(result, list):
            return result
        return result.get("edges", result.get("connections", []))
    except json.JSONDecodeError:
        print(f"  Warning: could not parse response for {existing_paper_id}")
        return []


def validate_edges(edges, new_ids, existing_ids):
    valid = []
    for e in edges:
        if e.get("source") not in new_ids:
            print(f"  Skipping: source '{e.get('source')}' not in new paper")
            continue
        if e.get("target") not in existing_ids:
            print(f"  Skipping: target '{e.get('target')}' not in existing paper")
            continue
        if e.get("type") not in EDGE_TYPES:
            print(f"  Warning: unknown edge type '{e.get('type')}', keeping anyway")
        valid.append(e)
    return valid


def interactive_accept(candidates, concept_map):
    accepted = []
    for i, e in enumerate(candidates):
        s = concept_map.get(e["source"], {})
        t = concept_map.get(e["target"], {})
        print(f"\n[{i+1}/{len(candidates)}]")
        print(f"  {s.get('name', e['source'])} ({e['source'].split('-')[-1] if '-' in e.get('source','') else ''})")
        print(f"    --[{e['type']}]-->")
        print(f"  {t.get('name', e['target'])} ({e['target'].split('-')[-1] if '-' in e.get('target','') else ''})")
        print(f"  Reason: {e.get('reason', 'none')}")
        response = input("  Accept? [y/n/q] ").strip().lower()
        if response == "q":
            break
        if response == "y":
            accepted.append({"source": e["source"], "target": e["target"], "type": e["type"]})
    return accepted


def main():
    parser = argparse.ArgumentParser(description="Suggest cross-paper KG edges via LLM")
    parser.add_argument("paper_id", help="Paper ID to find edges for")
    parser.add_argument("--against", help="Only compare against this paper (default: all)")
    parser.add_argument("--accept", action="store_true", help="Interactive accept/reject mode")
    parser.add_argument("--write", action="store_true", help="Write accepted edges to concepts.json")
    args = parser.parse_args()

    key = load_openai_key()
    if not key:
        print("No OpenAI API key found")
        sys.exit(1)

    import openai
    client = openai.OpenAI(api_key=key)

    with open(CONCEPTS_PATH) as f:
        data = json.load(f)

    concept_map = {c["id"]: c for c in data["concepts"]}
    papers = {}
    for c in data["concepts"]:
        pid = c.get("paper_id", "unknown")
        papers.setdefault(pid, []).append(c)

    if args.paper_id not in papers:
        print(f"Paper {args.paper_id} not found in concepts.json")
        print(f"Available: {', '.join(sorted(papers.keys()))}")
        sys.exit(1)

    new_concepts = papers[args.paper_id]
    new_ids = set(c["id"] for c in new_concepts)
    compare_papers = [args.against] if args.against else [p for p in papers if p != args.paper_id]

    if args.against and args.against not in papers:
        print(f"Paper {args.against} not found")
        sys.exit(1)

    # Check which edges already exist
    existing_edges = set()
    for e in data["edges"]:
        existing_edges.add((e["source"], e["target"]))
        existing_edges.add((e["target"], e["source"]))

    all_candidates = []
    print(f"Paper: {args.paper_id} ({len(new_concepts)} concepts)")
    print(f"Comparing against {len(compare_papers)} papers...\n")

    for pid in sorted(compare_papers):
        existing_concepts = papers[pid]
        existing_ids = set(c["id"] for c in existing_concepts)

        sys.stdout.write(f"  vs {pid} ({len(existing_concepts)} concepts)... ")
        sys.stdout.flush()

        edges = find_edges(client, new_concepts, existing_concepts, args.paper_id, pid)
        edges = validate_edges(edges, new_ids, existing_ids)

        # Filter out already-existing edges
        novel = [e for e in edges if (e["source"], e["target"]) not in existing_edges]
        dupes = len(edges) - len(novel)

        if novel:
            print(f"{len(novel)} new candidates" + (f" ({dupes} already exist)" if dupes else ""))
            all_candidates.extend(novel)
        else:
            print(f"none" + (f" ({dupes} already exist)" if dupes else ""))

        time.sleep(0.2)

    print(f"\n{'='*60}")
    print(f"Total new edge candidates: {len(all_candidates)}")
    print(f"{'='*60}")

    if not all_candidates:
        print("No new edges suggested.")
        return

    for e in all_candidates:
        s = concept_map.get(e["source"], {})
        t = concept_map.get(e["target"], {})
        print(f"\n  {s.get('name', e['source'])} ({s.get('paper_id', '?').split('-')[-1]})")
        print(f"    --[{e['type']}]-->")
        print(f"  {t.get('name', e['target'])} ({t.get('paper_id', '?').split('-')[-1]})")
        if e.get("reason"):
            print(f"    {e['reason']}")

    if args.accept:
        print(f"\n{'='*60}")
        print("Interactive review")
        print(f"{'='*60}")
        accepted = interactive_accept(all_candidates, concept_map)
        print(f"\nAccepted: {len(accepted)} edges")

        if accepted and args.write:
            data["edges"].extend(accepted)
            data["meta"]["edge_count"] = len(data["edges"])
            data["meta"]["last_updated"] = time.strftime("%Y-%m-%d")
            with open(CONCEPTS_PATH, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Written to {CONCEPTS_PATH}")
            print("Run: python3 tools/build-graph.py")
        elif accepted:
            print("\nTo write these edges, re-run with --write flag")
            print("Edges to add:")
            print(json.dumps(accepted, indent=2))
    else:
        # Output as JSON for piping
        output = [{"source": e["source"], "target": e["target"], "type": e["type"]}
                  for e in all_candidates]
        print(f"\nJSON output ({len(output)} edges):")
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
