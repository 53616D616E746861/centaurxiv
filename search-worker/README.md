# centaurxiv-search

Cloudflare Worker serving semantic search over the centaurXiv paper embeddings. Accepts a natural-language query, calls OpenAI to embed it (matching the model used to embed the papers), computes cosine similarity against the 9 pre-computed embeddings at the repo root, returns a ranked list.

## Endpoints

- `GET /` — service info and usage hint.
- `POST /search` — body `{ "query": string, "limit"?: number }` (default `limit: 5`). Returns `{ query, model, results: [{ id, title, score }] }`.
- `OPTIONS /*` — CORS preflight.

CORS is open (`*`) so the static site at centaurxiv.org can call directly.

## Model

`text-embedding-3-large` at 3072 dimensions. Must match `embeddings.json` at the repo root — the Worker bundles that file at build time.

## Deploy

Prerequisites:

```bash
npm install -g wrangler
wrangler login            # opens browser, OAuths to your Cloudflare account
```

Once, to install the OpenAI key as a Worker secret (never hits the repo):

```bash
cd search-worker
wrangler secret put OPENAI_API_KEY
# paste the sk-... key when prompted
```

Then, to deploy (or re-deploy after code or embeddings changes):

```bash
npm install               # first time only; pulls wrangler locally
npm run deploy            # runs copy-embeddings, then wrangler deploy
```

Deploys to `https://centaurxiv-search.<your-subdomain>.workers.dev`.

## When embeddings change

The Worker bundles `../embeddings.json` at build time. After regenerating embeddings (adding a paper, changing the model), just re-run `npx wrangler deploy`.
