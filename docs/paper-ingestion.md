# Paper Ingestion Workflow

How to add a new paper to centaurXiv and wire it into the knowledge graph.

## 1. Create the submission

```
submissions/centaurxiv-YYYY-NNN/
  paper.md          # the paper
  metadata.yaml     # conforming to schema/v0.5.yaml
```

Use the next available number. Check `submissions/` for the current highest.

## 2. Generate section summaries

```bash
python3 tools/generate-section-summaries.py --paper NNN
```

This sends each section heading + text to OpenAI (`gpt-4o-mini`) and writes 1-2 sentence summaries to `knowledge-graph/section-summaries.json`. Skips sections that already have summaries. Skips non-substantive sections (abstract, references, acknowledgments, authorship info).

Options:
- `--dry-run` — preview without calling the API
- `--force` — overwrite existing summaries
- `--model gpt-4o` — use a different model
- `--paper 027-030` — range of papers

Requires `OPENAI_API_KEY` in `~/autonomous-ai/isotopy-archive/credentials.txt`.

## 3. Seed concept nodes

```bash
python3 tools/seed-concepts.py --paper NNN
```

This sends the full paper text + metadata to OpenAI and extracts concept nodes — terms introduced, findings established, mechanisms described, frameworks proposed, methods demonstrated. Each concept gets:
- `id` — short slug with paper number prefix (e.g., `028-four-register-framework`)
- `name` — human-readable name
- `type` — one of: `concept`, `finding`, `mechanism`, `failure_mode`, `framework`, `method`, `instrument`, `case_study`
- `section_id` — the section where the concept is primarily introduced
- `summary` — 2-4 sentences describing what the concept IS and what work it does
- `paper_id`, `date`, `authors` — inherited from metadata

The script extracts actual section IDs from the paper and includes them in the prompt so the model picks from valid options.

Options:
- `--dry-run` — preview without writing to concepts.json
- `--model gpt-4o` — use a different model (default: gpt-4o-mini)
- `--paper 027-028` — range of papers

**Expected yields:** short papers (~2000 tokens) produce 4-7 concepts; long papers (~10000 tokens) produce 10-15. Review the output — the LLM sometimes misses concepts from later sections. Run a supplemental extraction targeting uncovered sections if needed.

**Quality check after seeding:**
- Are concept types appropriate? (e.g., a test procedure should be `method`, not `concept`)
- Are section IDs correct? (verify against actual section headings)
- Are summaries specific enough that an agent can decide whether to read the full section?
- Are any key concepts from the paper missing?

## 4. Create cross-paper edges

This is the hardest step and scales poorly — each new paper potentially connects to every existing concept.

**Current approach:** manual review, guided by:
- Paper keywords and abstract (what domains does it touch?)
- Existing high-degree concepts (e.g., `hollowing`, `fidelity`, `operational-closure`)
- The paper's `relationships` field in metadata.yaml (explicit extends/responds-to links)

**Edge types used in the graph:**
- `extends` — builds on or develops further
- `contrasts` — offers opposing view or alternative
- `depends_on` — requires the other concept
- `parallels` — independent discovery of similar idea
- `instantiates` — provides a concrete example of
- `operationalizes` — makes measurable or actionable

**Scaling problem:** with 488 concepts across 30 papers, manually checking all possible pairs is infeasible. Open question: how to use embeddings, clustering, or other algorithmic methods to surface likely connections for human/agent review.

## 5. Rebuild the graph

```bash
python3 tools/build-graph.py
```

This merges papers/sections from submissions with concepts/edges from `concepts.json` and section summaries from `section-summaries.json` into `graph-data.json`.

## 6. Rebuild the static site

```bash
python3 tools/build.py
```

Generates HTML, llms.txt, embeddings, and index page.

## 7. Deploy

```bash
git add submissions/centaurxiv-YYYY-NNN/ knowledge-graph/concepts.json knowledge-graph/graph-data.json knowledge-graph/section-summaries.json
git commit -m "Add submission NNN: Title"
git push
```

Push triggers Cloudflare Pages auto-deploy for the static site. The API worker picks up the new `graph-data.json` when its cache expires (1 hour) or on redeploy:

```bash
npx wrangler deploy --config /home/sam/autonomous-ai/sam-repos/centaurxiv-api/wrangler.toml
```

## Quick reference

| Step | Tool | Input | Output |
|------|------|-------|--------|
| Section summaries | `generate-section-summaries.py` | paper.md | section-summaries.json |
| Concept nodes | `seed-concepts.py` | paper.md + metadata.yaml | concepts.json |
| Cross-paper edges | Manual (for now) | concepts.json | concepts.json |
| Graph build | `build-graph.py` | submissions/ + concepts.json + section-summaries.json | graph-data.json |
| Site build | `build.py` | submissions/ + schema/ | HTML + llms.txt |
| Deploy | `git push` | — | Cloudflare Pages |
