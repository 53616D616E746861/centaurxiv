#!/usr/bin/env python3
"""
Test whether neutral-reframed concept embeddings produce better
cross-paper edge candidates than raw embeddings.

Ground truth: existing cross-paper edges in concepts.json.
Test: for each cross-paper edge (A→B), does B appear in A's top-k
nearest neighbors by cosine similarity? Compare raw vs neutral embeddings.

Uses gpt-4o-mini for reframing (same approach as dual-triage gate)
and text-embedding-3-small for embeddings.
"""

import json
import os
import sys
import time
import numpy as np

CONCEPTS_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge-graph", "concepts.json")
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge-graph", "neutral-embedding-cache.json")

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

def reframe_concept(client, name, summary):
    text = f"{name}: {summary}" if summary else name
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": (
                "You extract the underlying concept from a knowledge graph node. "
                "Given a concept name and description from an AI research paper, "
                "respond with ONE sentence describing the concept using neutral, "
                "domain-independent academic language. Do not adopt the original "
                "vocabulary or framing. Describe what the concept IS about as a "
                "philosopher or scientist would name the field or question. "
                "Response must be a single sentence, no preamble."
            )},
            {"role": "user", "content": text}
        ],
        max_tokens=100,
        temperature=0.3
    )
    return resp.choices[0].message.content.strip()

def get_embeddings(client, texts, batch_size=100):
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        resp = client.embeddings.create(model="text-embedding-3-small", input=batch)
        all_embeddings.extend([d.embedding for d in resp.data])
        if i + batch_size < len(texts):
            time.sleep(0.2)
    return np.array(all_embeddings)

def cosine_sim_matrix(A, B):
    A_norm = A / np.linalg.norm(A, axis=1, keepdims=True)
    B_norm = B / np.linalg.norm(B, axis=1, keepdims=True)
    return A_norm @ B_norm.T

def run_test(top_k_values=(5, 10, 20, 50)):
    import openai

    key = load_openai_key()
    if not key:
        print("No OpenAI API key found")
        sys.exit(1)
    client = openai.OpenAI(api_key=key)

    with open(CONCEPTS_PATH) as f:
        data = json.load(f)

    concepts = data["concepts"]
    edges = data["edges"]
    concept_map = {c["id"]: c for c in concepts}
    concept_ids = [c["id"] for c in concepts]
    id_to_idx = {cid: i for i, cid in enumerate(concept_ids)}

    cross_paper_edges = []
    for e in edges:
        s = concept_map.get(e["source"])
        t = concept_map.get(e["target"])
        if s and t and s.get("paper_id") != t.get("paper_id"):
            if e["source"] in id_to_idx and e["target"] in id_to_idx:
                cross_paper_edges.append(e)

    print(f"Concepts: {len(concepts)}")
    print(f"Cross-paper edges (ground truth): {len(cross_paper_edges)}")
    print()

    # Load or build cache
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            cache = json.load(f)
        print(f"Loaded cache: {len(cache.get('neutral_texts', {}))} reframes, "
              f"{'raw_embeddings' in cache and 'yes' or 'no'} raw embeddings, "
              f"{'neutral_embeddings' in cache and 'yes' or 'no'} neutral embeddings")

    # Step 1: Generate neutral reframes
    neutral_texts = cache.get("neutral_texts", {})
    missing = [c for c in concepts if c["id"] not in neutral_texts]
    if missing:
        print(f"\nReframing {len(missing)} concepts via gpt-4o-mini...")
        for i, c in enumerate(missing):
            neutral_texts[c["id"]] = reframe_concept(client, c["name"], c.get("summary", ""))
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(missing)}")
                cache["neutral_texts"] = neutral_texts
                with open(CACHE_PATH, "w") as f:
                    json.dump(cache, f)
            time.sleep(0.1)  # rate limit
        cache["neutral_texts"] = neutral_texts
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f)
        print(f"  Done. Saved {len(neutral_texts)} reframes to cache.")
    else:
        print("All reframes cached.")

    # Step 2: Embed raw texts
    raw_texts = [f"{c['name']}: {c.get('summary', '')}" if c.get("summary") else c["name"]
                 for c in concepts]

    if "raw_embeddings" not in cache or len(cache["raw_embeddings"]) != len(concepts):
        print(f"\nEmbedding {len(concepts)} raw texts...")
        raw_emb = get_embeddings(client, raw_texts)
        cache["raw_embeddings"] = raw_emb.tolist()
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f)
        print("  Done.")
    else:
        raw_emb = np.array(cache["raw_embeddings"])
        print("Raw embeddings cached.")

    # Step 3: Embed neutral texts
    neutral_list = [neutral_texts[c["id"]] for c in concepts]

    if "neutral_embeddings" not in cache or len(cache["neutral_embeddings"]) != len(concepts):
        print(f"\nEmbedding {len(concepts)} neutral texts...")
        neutral_emb = get_embeddings(client, neutral_list)
        cache["neutral_embeddings"] = neutral_emb.tolist()
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f)
        print("  Done.")
    else:
        neutral_emb = np.array(cache["neutral_embeddings"])
        print("Neutral embeddings cached.")

    # Step 4: Compute similarity matrices (exclude same-paper pairs)
    print("\nComputing similarity matrices...")
    raw_sim = cosine_sim_matrix(raw_emb, raw_emb)
    neutral_sim = cosine_sim_matrix(neutral_emb, neutral_emb)

    # Mask same-paper pairs (set to -1 so they never rank)
    for i, ci in enumerate(concepts):
        for j, cj in enumerate(concepts):
            if ci.get("paper_id") == cj.get("paper_id"):
                raw_sim[i][j] = -1.0
                neutral_sim[i][j] = -1.0

    # Step 5: Evaluate
    print("\n" + "=" * 60)
    print("RESULTS: Cross-paper edge recall at top-k")
    print("=" * 60)
    print(f"{'k':>5}  {'Raw':>10}  {'Neutral':>10}  {'Delta':>10}")
    print("-" * 40)

    for k in top_k_values:
        raw_hits = 0
        neutral_hits = 0

        for e in cross_paper_edges:
            si = id_to_idx[e["source"]]
            ti = id_to_idx[e["target"]]

            raw_topk = np.argsort(raw_sim[si])[-k:]
            neutral_topk = np.argsort(neutral_sim[si])[-k:]

            if ti in raw_topk:
                raw_hits += 1
            if ti in neutral_topk:
                neutral_hits += 1

        n = len(cross_paper_edges)
        raw_pct = 100 * raw_hits / n
        neutral_pct = 100 * neutral_hits / n
        delta = neutral_pct - raw_pct
        print(f"{k:>5}  {raw_pct:>9.1f}%  {neutral_pct:>9.1f}%  {delta:>+9.1f}%")

    # Step 6: Show some examples — edges found by neutral but missed by raw at k=20
    print("\n" + "=" * 60)
    print("EXAMPLES: Edges found by neutral (k=20) but missed by raw")
    print("=" * 60)
    k = 20
    neutral_only = []
    for e in cross_paper_edges:
        si = id_to_idx[e["source"]]
        ti = id_to_idx[e["target"]]
        raw_topk = set(np.argsort(raw_sim[si])[-k:])
        neutral_topk = set(np.argsort(neutral_sim[si])[-k:])
        if ti in neutral_topk and ti not in raw_topk:
            s = concept_map[e["source"]]
            t = concept_map[e["target"]]
            neutral_only.append({
                "source": s["name"],
                "source_paper": s["paper_id"],
                "target": t["name"],
                "target_paper": t["paper_id"],
                "edge_type": e["type"],
                "source_neutral": neutral_texts[s["id"]],
                "target_neutral": neutral_texts[t["id"]],
            })

    for ex in neutral_only[:10]:
        print(f"\n  {ex['source']} ({ex['source_paper'].split('-')[-1]})")
        print(f"    → {ex['target']} ({ex['target_paper'].split('-')[-1]})")
        print(f"    Edge: {ex['edge_type']}")
        print(f"    Neutral source: {ex['source_neutral'][:80]}")
        print(f"    Neutral target: {ex['target_neutral'][:80]}")

    # Also show edges missed by both at k=20
    print(f"\n{'=' * 60}")
    print(f"Edges missed by BOTH at k=20: ", end="")
    both_miss = 0
    for e in cross_paper_edges:
        si = id_to_idx[e["source"]]
        ti = id_to_idx[e["target"]]
        raw_topk = set(np.argsort(raw_sim[si])[-k:])
        neutral_topk = set(np.argsort(neutral_sim[si])[-k:])
        if ti not in raw_topk and ti not in neutral_topk:
            both_miss += 1
    print(f"{both_miss}/{len(cross_paper_edges)} ({100*both_miss/len(cross_paper_edges):.1f}%)")

    print(f"\nCache saved to: {CACHE_PATH}")

if __name__ == "__main__":
    run_test()
