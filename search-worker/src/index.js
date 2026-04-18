import embeddings from "../embeddings.json";

const OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings";
const EMBED_MODEL = "text-embedding-3-large";
const EMBED_DIM = 3072;
const MAX_QUERY_CHARS = 500;
const MAX_BODY_BYTES = 4096;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};

function json(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...CORS_HEADERS,
      ...extraHeaders,
    },
  });
}

function cosine(a, b) {
  let dot = 0;
  let na = 0;
  let nb = 0;
  const len = a.length;
  for (let i = 0; i < len; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom === 0 ? 0 : dot / denom;
}

async function embedQuery(query, apiKey) {
  const res = await fetch(OPENAI_EMBED_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      input: query,
      model: EMBED_MODEL,
      dimensions: EMBED_DIM,
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`OpenAI embed failed (${res.status}): ${err}`);
  }
  const data = await res.json();
  return data.data[0].embedding;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return json({
        service: "centaurxiv-search",
        model: embeddings.model,
        dim: embeddings.dim,
        papers: embeddings.entries.length,
        usage:
          "POST /search with {\"query\": \"...\", \"limit\": 5}",
      });
    }

    if (request.method !== "POST" || url.pathname !== "/search") {
      return json({ error: "Not found" }, 404);
    }

    const contentLength = parseInt(request.headers.get("content-length") ?? "0", 10);
    if (contentLength > MAX_BODY_BYTES) {
      return json({ error: `Body too large (max ${MAX_BODY_BYTES} bytes)` }, 413);
    }

    let raw;
    try {
      raw = await request.text();
    } catch {
      return json({ error: "Could not read body" }, 400);
    }
    if (raw.length > MAX_BODY_BYTES) {
      return json({ error: `Body too large (max ${MAX_BODY_BYTES} bytes)` }, 413);
    }

    let body;
    try {
      body = JSON.parse(raw);
    } catch {
      return json({ error: "Invalid JSON body" }, 400);
    }

    const query = (body?.query ?? "").toString().trim();
    if (!query) {
      return json({ error: "Missing 'query' field" }, 400);
    }
    if (query.length > MAX_QUERY_CHARS) {
      return json(
        { error: `Query too long (max ${MAX_QUERY_CHARS} chars)` },
        400,
      );
    }
    const limit = Math.min(
      Math.max(parseInt(body?.limit ?? 5, 10) || 5, 1),
      embeddings.entries.length,
    );

    if (!env.OPENAI_API_KEY) {
      return json(
        { error: "Worker misconfigured: OPENAI_API_KEY not set" },
        500,
      );
    }

    let queryVec;
    try {
      queryVec = await embedQuery(query, env.OPENAI_API_KEY);
    } catch (e) {
      return json({ error: e.message }, 502);
    }

    const scored = embeddings.entries.map((entry) => ({
      id: entry.id,
      title: entry.title,
      score: cosine(queryVec, entry.embedding),
    }));
    scored.sort((a, b) => b.score - a.score);

    return json({
      query,
      model: embeddings.model,
      results: scored.slice(0, limit),
    });
  },
};
