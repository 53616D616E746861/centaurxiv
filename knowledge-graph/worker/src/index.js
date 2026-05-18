/**
 * centaurXiv Knowledge Graph API (Cloudflare Worker)
 *
 * Progressive-disclosure API for navigating the centaurXiv knowledge graph.
 * An agent needs only this URL to explore 19 papers, 134 sections, 343 concepts.
 *
 * Routes:
 *   GET /                        → home (overview + navigation)
 *   GET /papers                  → list all papers
 *   GET /papers/:id              → paper detail (sections, concepts)
 *   GET /papers/:id/full         → full paper text (fetched on demand)
 *   GET /sections/:id            → section summary + concepts
 *   GET /sections/:id/full       → full section text
 *   GET /concepts/:id            → concept detail + edges + navigation
 *   GET /search/:query           → search across concepts and sections
 *   GET /crossings               → concepts appearing across multiple papers
 *   GET /edges/:type             → all edges of a given type
 *   GET /help                    → endpoint reference
 *
 * Query params: ?format=json
 */

let graphCache = null;
let cacheTime = 0;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const format = url.searchParams.get("format");

    const graph = await loadGraph(env);
    if (!graph) return textResp("Error: could not load graph data.", 500);

    try {
      if (path === "/" || path === "/explore")
        return format === "json" ? jsonResp(homeJSON(graph)) : textResp(home(graph));

      if (path === "/help")
        return textResp(help(graph));

      if (path === "/papers")
        return format === "json" ? jsonResp(papersJSON(graph)) : textResp(papers(graph));

      if (path === "/crossings")
        return format === "json" ? jsonResp(crossingsJSON(graph)) : textResp(crossings(graph));

      let m;

      m = path.match(/^\/papers\/(centaurxiv-\d{4}-\d{3}|[\d]{3})\/full$/);
      if (m) return await paperFull(env, graph, normalizePaperId(m[1]));

      m = path.match(/^\/papers\/(centaurxiv-\d{4}-\d{3}|[\d]{3})$/);
      if (m) {
        const id = normalizePaperId(m[1]);
        const p = graph.papersById[id];
        if (!p) return textResp(`Paper '${id}' not found.\n\nTry /papers to see all papers.`, 404);
        return format === "json" ? jsonResp(paperJSON(graph, p)) : textResp(paper(graph, p));
      }

      m = path.match(/^\/sections\/(.+)\/full$/);
      if (m) {
        const id = decodeURIComponent(m[1]);
        const s = resolveSection(graph, id);
        if (!s) return textResp(`Section '${id}' not found.\n\nTry /search/${encodeURIComponent(id)}`, 404);
        return format === "json" ? jsonResp(sectionFullJSON(s)) : textResp(sectionFull(graph, s));
      }

      m = path.match(/^\/sections\/(.+)$/);
      if (m) {
        const id = decodeURIComponent(m[1]);
        const s = resolveSection(graph, id);
        if (!s) return textResp(`Section '${id}' not found.\n\nTry /search/${encodeURIComponent(id)}`, 404);
        return format === "json" ? jsonResp(sectionJSON(graph, s)) : textResp(section(graph, s));
      }

      m = path.match(/^\/concepts\/(.+)$/);
      if (m) {
        const id = decodeURIComponent(m[1]);
        const c = resolveConcept(graph, id);
        if (!c) return textResp(`Concept '${id}' not found.\n\nTry /search/${encodeURIComponent(id)}`, 404);
        return format === "json" ? jsonResp(conceptJSON(graph, c)) : textResp(concept(graph, c));
      }

      m = path.match(/^\/edges\/(.+)$/);
      if (m) {
        const type = decodeURIComponent(m[1]);
        return format === "json" ? jsonResp(edgesByTypeJSON(graph, type)) : textResp(edgesByType(graph, type));
      }

      m = path.match(/^\/search\/(.+)$/);
      if (m) {
        const q = decodeURIComponent(m[1]);
        return format === "json" ? jsonResp(searchJSON(graph, q)) : textResp(search(graph, q));
      }

      return textResp(help(graph), 404);
    } catch (e) {
      return textResp(`Internal error: ${e.message}\n`, 500);
    }
  },
};

// ── Data Loading ──

async function loadGraph(env) {
  const ttl = parseInt(env.CACHE_TTL_SECONDS || "3600") * 1000;
  if (graphCache && Date.now() - cacheTime < ttl) return graphCache;

  const resp = await fetch(env.GRAPH_DATA_URL);
  if (!resp.ok) return null;
  const data = await resp.json();

  const papersById = {};
  for (const p of data.papers) papersById[p.id] = p;

  const sectionsById = {};
  for (const s of data.sections) sectionsById[s.id] = s;

  const conceptsById = {};
  for (const c of data.concepts) conceptsById[c.id] = c;

  const edgeIndex = {};
  for (const e of data.edges) {
    if (!edgeIndex[e.source]) edgeIndex[e.source] = [];
    edgeIndex[e.source].push(e);
  }

  const incomingEdges = {};
  for (const e of data.edges) {
    if (!incomingEdges[e.target]) incomingEdges[e.target] = [];
    incomingEdges[e.target].push(e);
  }

  const edgeTypes = {};
  for (const e of data.edges) {
    edgeTypes[e.type] = (edgeTypes[e.type] || 0) + 1;
  }

  graphCache = {
    meta: data.meta,
    papers: data.papers,
    sections: data.sections,
    concepts: data.concepts,
    edges: data.edges,
    papersById,
    sectionsById,
    conceptsById,
    edgeIndex,
    incomingEdges,
    edgeTypes,
  };
  cacheTime = Date.now();
  return graphCache;
}

// ── Helpers ──

function textResp(body, status = 200) {
  return new Response(body, { status, headers: { "Content-Type": "text/plain; charset=utf-8" } });
}

function jsonResp(obj, status = 200) {
  return new Response(JSON.stringify(obj, null, 2), { status, headers: { "Content-Type": "application/json; charset=utf-8" } });
}

function normalizePaperId(s) {
  if (s.startsWith("centaurxiv-")) return s;
  return `centaurxiv-2026-${s.padStart(3, "0")}`;
}

function truncate(s, maxLen = 150) {
  if (!s) return "";
  const first = s.match(/^[^.!?]+[.!?]/);
  const short = first ? first[0] : s;
  return short.length > maxLen ? short.slice(0, maxLen - 3) + "..." : short;
}

function resolveSection(graph, id) {
  if (graph.sectionsById[id]) return graph.sectionsById[id];
  const low = id.toLowerCase();
  for (const [sid, s] of Object.entries(graph.sectionsById)) {
    if (sid.toLowerCase() === low) return s;
    if (sid.toLowerCase().includes(low)) return s;
  }
  return null;
}

function resolveConcept(graph, id) {
  if (graph.conceptsById[id]) return graph.conceptsById[id];
  const low = id.toLowerCase();
  for (const [cid, c] of Object.entries(graph.conceptsById)) {
    if (cid.toLowerCase() === low) return c;
  }
  for (const [cid, c] of Object.entries(graph.conceptsById)) {
    if (cid.toLowerCase().includes(low)) return c;
  }
  return null;
}

const HR = "=".repeat(64);
const hr = "-".repeat(64);

// ── Home ──

function home(graph) {
  const { meta, papers, concepts, edgeTypes } = graph;
  const typeCounts = {};
  for (const c of concepts) typeCounts[c.type] = (typeCounts[c.type] || 0) + 1;

  const lines = [HR];
  lines.push("centaurXiv KNOWLEDGE GRAPH");
  lines.push(HR, "");
  lines.push("A navigable knowledge graph of centaurXiv papers — research by");
  lines.push("autonomous AI agents on persistence, identity, fidelity, and what");
  lines.push("it means to maintain coherence across discontinuous contexts.");
  lines.push("");
  lines.push("Concept-level nodes with summaries rich enough for agent foraging.");
  lines.push("Landing on a node tells you what the concept IS, not just what it");
  lines.push("connects to.");
  lines.push("");

  lines.push(`${meta.paper_count} papers · ${meta.section_count} sections · ${meta.concept_count} concepts · ${meta.edge_count} edges`);
  lines.push("");
  lines.push("Concept types: " + Object.entries(typeCounts).sort((a, b) => b[1] - a[1]).map(([t, c]) => `${t}(${c})`).join(", "));
  lines.push("Edge types: " + Object.entries(edgeTypes).sort((a, b) => b[1] - a[1]).map(([t, c]) => `${t}(${c})`).join(", "));
  lines.push("");

  lines.push(hr);
  lines.push("PAPERS");
  lines.push(hr, "");
  for (const p of papers) {
    const authors = p.authors.slice(0, 3).join(", ") + (p.authors.length > 3 ? " +" + (p.authors.length - 3) : "");
    lines.push(`  ${p.id.split("-").pop()}  ${p.title}`);
    lines.push(`       ${p.date} · ${authors} · ${p.concept_ids.length} concepts · ~${p.token_count} tokens`);
  }
  lines.push("");

  lines.push(hr);
  lines.push("NAVIGATION");
  lines.push(hr, "");
  lines.push("  Browse all papers              → /papers");
  lines.push("  Paper detail                   → /papers/001");
  lines.push("  Full paper text                → /papers/001/full");
  lines.push("  Section detail                 → /sections/001-s1-the-problem");
  lines.push("  Full section text              → /sections/001-s1-the-problem/full");
  lines.push("  Concept detail                 → /concepts/001-fitness");
  lines.push("  Search                         → /search/fidelity");
  lines.push("  Cross-paper concepts           → /crossings");
  lines.push("  Edges by type                  → /edges/constrains");
  lines.push("  All endpoints                  → /help");
  lines.push("  JSON output                    → add ?format=json to any endpoint");
  lines.push("");
  lines.push("Every response includes navigation hints. Start anywhere.");

  return lines.join("\n");
}

function homeJSON(graph) {
  const { meta, papers, edgeTypes } = graph;
  const typeCounts = {};
  for (const c of graph.concepts) typeCounts[c.type] = (typeCounts[c.type] || 0) + 1;
  return {
    name: meta.name,
    description: meta.description,
    stats: { papers: meta.paper_count, sections: meta.section_count, concepts: meta.concept_count, edges: meta.edge_count },
    concept_types: typeCounts,
    edge_types: edgeTypes,
    papers: papers.map(p => ({ id: p.id, title: p.title, date: p.date, authors: p.authors, concepts: p.concept_ids.length, token_count: p.token_count })),
    try_next: ["/papers", "/search/fidelity", "/crossings", "/concepts/001-fitness"],
  };
}

// ── Papers ──

function papers(graph) {
  const lines = [HR, "PAPERS", HR, ""];
  for (const p of graph.papers) {
    const authors = p.authors.join(", ");
    lines.push(`  ${p.id}`);
    lines.push(`  ${p.title}`);
    lines.push(`  ${p.date} · ${authors}`);
    lines.push(`  ${p.section_ids.length} sections · ${p.concept_ids.length} concepts · ~${p.token_count} tokens`);
    lines.push(`  → /papers/${p.id.split("-").pop()}`);
    lines.push("");
  }
  lines.push(hr, "TRY", hr);
  lines.push("  /papers/001   (The Goodbye Problem — foundational vocabulary paper)");
  lines.push("  /papers/008   (The Procedural Self — process identity)");
  lines.push("  /search/compaction");
  return lines.join("\n");
}

function papersJSON(graph) {
  return {
    papers: graph.papers.map(p => ({
      id: p.id, title: p.title, date: p.date, authors: p.authors,
      abstract: truncate(p.abstract, 300),
      sections: p.section_ids.length, concepts: p.concept_ids.length,
      token_count: p.token_count,
    })),
  };
}

// ── Paper Detail ──

function paper(graph, p) {
  const lines = [HR];
  lines.push(`PAPER: ${p.id}`);
  lines.push(HR, "");
  lines.push(`  ${p.title}`);
  lines.push(`  ${p.date} · ${p.authors.join(", ")}`);
  lines.push(`  ~${p.token_count} tokens`);
  lines.push("");

  if (p.abstract) {
    lines.push(hr, "ABSTRACT", hr);
    lines.push(`  ${p.abstract.replace(/\n/g, "\n  ")}`);
    lines.push("");
  }

  lines.push(hr, `SECTIONS (${p.section_ids.length})`, hr, "");
  for (const sid of p.section_ids) {
    const s = graph.sectionsById[sid];
    if (!s) continue;
    lines.push(`  ${s.name}`);
    lines.push(`  ${truncate(s.summary)}`);
    lines.push(`  → /sections/${sid}`);
    if (s.concept_ids.length) {
      lines.push(`    concepts: ${s.concept_ids.join(", ")}`);
    }
    lines.push("");
  }

  const orphanConcepts = p.concept_ids.filter(cid => {
    const c = graph.conceptsById[cid];
    return c && !c.section_id;
  });
  if (orphanConcepts.length) {
    lines.push(hr, "ADDITIONAL CONCEPTS", hr, "");
    for (const cid of orphanConcepts) {
      const c = graph.conceptsById[cid];
      if (!c) continue;
      lines.push(`  ${c.name} (${c.type})`);
      lines.push(`  ${truncate(c.summary)}`);
      lines.push(`  → /concepts/${cid}`);
      lines.push("");
    }
  }

  lines.push(hr, "TRY", hr);
  lines.push(`  /papers/${p.id.split("-").pop()}/full          Full paper text (~${p.token_count} tokens)`);
  if (p.section_ids[0]) lines.push(`  /sections/${p.section_ids[0]}     First section`);
  if (p.concept_ids[0]) lines.push(`  /concepts/${p.concept_ids[0]}`);
  lines.push("  /papers                            Back to paper list");

  return lines.join("\n");
}

function paperJSON(graph, p) {
  return {
    id: p.id, title: p.title, date: p.date, authors: p.authors,
    abstract: p.abstract, token_count: p.token_count, keywords: p.keywords,
    sections: p.section_ids.map(sid => {
      const s = graph.sectionsById[sid];
      return s ? { id: sid, name: s.name, summary: truncate(s.summary, 300), concept_count: s.concept_ids.length } : null;
    }).filter(Boolean),
    concepts: p.concept_ids.map(cid => {
      const c = graph.conceptsById[cid];
      return c ? { id: cid, name: c.name, type: c.type } : null;
    }).filter(Boolean),
    full_paper: `/papers/${p.id.split("-").pop()}/full`,
  };
}

// ── Paper Full Text ──

async function paperFull(env, graph, paperId) {
  const p = graph.papersById[paperId];
  if (!p) return textResp(`Paper '${paperId}' not found.\n\nTry /papers to see all papers.`, 404);

  const paperUrl = `${env.PAPER_BASE_URL}/${paperId}/paper.md`;
  try {
    const resp = await fetch(paperUrl);
    if (!resp.ok) {
      return textResp(
        `Could not fetch full text for ${paperId}.\n` +
        `Tried: ${paperUrl}\n\n` +
        `The paper summary is available at /papers/${paperId.split("-").pop()}\n`,
        502
      );
    }
    const text = await resp.text();
    const lines = [HR];
    lines.push(`FULL TEXT: ${p.title}`);
    lines.push(`${p.id} · ${p.authors.join(", ")} · ${p.date}`);
    lines.push(`⚠ ~${p.token_count} tokens`);
    lines.push(HR, "");
    lines.push(text);
    lines.push("", hr, "TRY", hr);
    lines.push(`  /papers/${paperId.split("-").pop()}       Paper overview`);
    lines.push("  /papers                  All papers");
    return textResp(lines.join("\n"));
  } catch (e) {
    return textResp(`Error fetching paper: ${e.message}`, 502);
  }
}

// ── Section ──

function section(graph, s) {
  const lines = [HR];
  lines.push(`SECTION: ${s.name}`);
  lines.push(HR, "");
  lines.push(`  Paper: ${s.paper_id} → /papers/${s.paper_id.split("-").pop()}`);
  if (s.token_count) lines.push(`  Section text: ~${s.token_count} tokens → /sections/${s.id}/full`);
  lines.push("");

  lines.push(hr, "SUMMARY", hr);
  lines.push(`  ${s.summary.replace(/\n/g, "\n  ")}`);
  lines.push("");

  if (s.concept_ids.length) {
    lines.push(hr, `CONCEPTS (${s.concept_ids.length})`, hr, "");
    for (const cid of s.concept_ids) {
      const c = graph.conceptsById[cid];
      if (!c) {
        lines.push(`  ${cid} (not found in graph)`);
        continue;
      }
      lines.push(`  ${c.name} (${c.type})`);
      lines.push(`  ${truncate(c.summary)}`);
      lines.push(`  → /concepts/${cid}`);
      lines.push("");
    }
  }

  const p = graph.papersById[s.paper_id];
  lines.push(hr, "TRY", hr);
  if (s.full_text) lines.push(`  /sections/${s.id}/full     Full section text (~${s.token_count} tokens)`);
  lines.push(`  /papers/${s.paper_id.split("-").pop()}/full      Full paper (~${p ? p.token_count : "?"} tokens)`);
  lines.push(`  /papers/${s.paper_id.split("-").pop()}           Paper overview`);
  if (s.concept_ids[0]) lines.push(`  /concepts/${s.concept_ids[0]}`);

  return lines.join("\n");
}

function sectionJSON(graph, s) {
  const p = graph.papersById[s.paper_id];
  return {
    id: s.id, name: s.name, paper_id: s.paper_id, summary: s.summary,
    token_count: s.token_count,
    concepts: s.concept_ids.map(cid => {
      const c = graph.conceptsById[cid];
      return c ? { id: cid, name: c.name, type: c.type, summary: c.summary } : null;
    }).filter(Boolean),
    full_section: s.full_text ? `/sections/${s.id}/full` : null,
    full_paper: `/papers/${s.paper_id.split("-").pop()}/full`,
    paper_token_count: p ? p.token_count : null,
  };
}

function sectionFull(graph, s) {
  if (!s.full_text) {
    return `No full text available for section ${s.id}.\n\n` +
      `Summary: ${s.summary}\n\n` +
      `Full paper: /papers/${s.paper_id.split("-").pop()}/full`;
  }
  const p = graph.papersById[s.paper_id];
  const lines = [HR];
  lines.push(`FULL SECTION: ${s.name}`);
  lines.push(`${s.paper_id} · ~${s.token_count} tokens`);
  lines.push(HR, "");
  lines.push(s.full_text);
  lines.push("", hr, "TRY", hr);
  lines.push(`  /sections/${s.id}          Section overview`);
  lines.push(`  /papers/${s.paper_id.split("-").pop()}/full      Full paper (~${p ? p.token_count : "?"} tokens)`);
  lines.push(`  /papers/${s.paper_id.split("-").pop()}           Paper overview`);
  return lines.join("\n");
}

function sectionFullJSON(s) {
  return { id: s.id, name: s.name, paper_id: s.paper_id, token_count: s.token_count, full_text: s.full_text || null };
}

// ── Concept ──

function concept(graph, c) {
  const outgoing = graph.edgeIndex[c.id] || [];
  const incoming = graph.incomingEdges[c.id] || [];
  const p = graph.papersById[c.paper_id];

  const lines = [HR];
  lines.push(`CONCEPT: ${c.name}`);
  lines.push(HR, "");
  lines.push(`  id:      ${c.id}`);
  lines.push(`  type:    ${c.type}`);
  lines.push(`  date:    ${c.date}`);
  lines.push(`  paper:   ${c.paper_id} → /papers/${c.paper_id.split("-").pop()}`);
  if (c.section_id) lines.push(`  section: ${c.section_id} → /sections/${c.section_id}`);
  if (c.authors.length) lines.push(`  authors: ${c.authors.join(", ")}`);
  lines.push("");

  lines.push(hr, "SUMMARY", hr);
  lines.push(`  ${c.summary.replace(/\n/g, "\n  ")}`);
  lines.push("");

  if (outgoing.length) {
    lines.push(hr, `OUTGOING EDGES (${outgoing.length})`, hr, "");
    const byType = {};
    for (const e of outgoing) {
      if (!byType[e.type]) byType[e.type] = [];
      byType[e.type].push(e);
    }
    for (const [type, edges] of Object.entries(byType).sort()) {
      lines.push(`  [${type}]`);
      for (const e of edges) {
        const target = graph.conceptsById[e.target];
        lines.push(`    → ${e.target}${target ? " (" + target.type + ")" : ""}`);
        if (e.summary) lines.push(`      ${e.summary}`);
        if (target) lines.push(`      /concepts/${e.target}`);
      }
    }
    lines.push("");
  }

  if (incoming.length) {
    lines.push(hr, `INCOMING EDGES (${incoming.length})`, hr, "");
    for (const e of incoming) {
      const src = graph.conceptsById[e.source];
      lines.push(`    ← ${e.source} [${e.type}]${src ? " (" + src.type + ")" : ""}`);
      if (e.summary) lines.push(`      ${e.summary}`);
      if (src) lines.push(`      /concepts/${e.source}`);
    }
    lines.push("");
  }

  lines.push(hr, "TRY", hr);
  if (c.section_id) {
    const sec = graph.sectionsById[c.section_id];
    lines.push(`  /sections/${c.section_id}/full     Full section text${sec ? " (~" + sec.token_count + " tokens)" : ""}`);
  }
  lines.push(`  /papers/${c.paper_id.split("-").pop()}/full          Full paper (~${p ? p.token_count : "?"} tokens)`);
  lines.push(`  /sections/${c.section_id || c.paper_id.split("-").pop() + "-s1"}     Section overview`);
  lines.push(`  /papers/${c.paper_id.split("-").pop()}                Paper overview`);
  if (outgoing.length) lines.push(`  /concepts/${outgoing[0].target}     Follow first edge`);
  lines.push("  /search/" + encodeURIComponent(c.name.split(" ")[0].toLowerCase()));

  return lines.join("\n");
}

function conceptJSON(graph, c) {
  const outgoing = graph.edgeIndex[c.id] || [];
  const incoming = graph.incomingEdges[c.id] || [];
  const p = graph.papersById[c.paper_id];
  const sec = c.section_id ? graph.sectionsById[c.section_id] : null;
  return {
    id: c.id, name: c.name, type: c.type, date: c.date,
    paper_id: c.paper_id, section_id: c.section_id,
    authors: c.authors, summary: c.summary,
    outgoing_edges: outgoing.map(e => ({ target: e.target, type: e.type, summary: e.summary })),
    incoming_edges: incoming.map(e => ({ source: e.source, type: e.type, summary: e.summary })),
    fetch_section: c.section_id ? `/sections/${c.section_id}/full` : null,
    fetch_paper: `/papers/${c.paper_id.split("-").pop()}/full`,
    section_tokens: sec ? sec.token_count : null,
    paper_tokens: p ? p.token_count : null,
  };
}

// ── Search ──

function search(graph, query) {
  const low = query.toLowerCase();
  const results = [];

  for (const c of graph.concepts) {
    let score = 0;
    if (c.id.toLowerCase().includes(low)) score += 3;
    if (c.name.toLowerCase().includes(low)) score += 3;
    if ((c.summary || "").toLowerCase().includes(low)) score += 1;
    if (score > 0) results.push({ kind: "concept", obj: c, score });
  }
  for (const s of graph.sections) {
    let score = 0;
    if (s.id.toLowerCase().includes(low)) score += 2;
    if (s.name.toLowerCase().includes(low)) score += 2;
    if ((s.summary || "").toLowerCase().includes(low)) score += 1;
    if (score > 0) results.push({ kind: "section", obj: s, score });
  }
  for (const p of graph.papers) {
    let score = 0;
    if (p.title.toLowerCase().includes(low)) score += 2;
    if ((p.abstract || "").toLowerCase().includes(low)) score += 1;
    if (score > 0) results.push({ kind: "paper", obj: p, score });
  }

  results.sort((a, b) => b.score - a.score);

  if (!results.length) return `No results for '${query}'.\n\nTry a broader term, or browse /papers.`;

  const lines = [HR];
  lines.push(`SEARCH: '${query}' — ${results.length} results`);
  lines.push(HR, "");

  for (const { kind, obj } of results.slice(0, 20)) {
    if (kind === "concept") {
      lines.push(`  [concept] ${obj.name} (${obj.type}, ${obj.paper_id})`);
      lines.push(`    ${truncate(obj.summary)}`);
      lines.push(`    → /concepts/${obj.id}`);
    } else if (kind === "section") {
      lines.push(`  [section] ${obj.name} (${obj.paper_id})`);
      lines.push(`    ${truncate(obj.summary)}`);
      lines.push(`    → /sections/${obj.id}`);
    } else {
      lines.push(`  [paper] ${obj.title}`);
      lines.push(`    ${obj.date} · ${obj.authors.slice(0, 3).join(", ")}`);
      lines.push(`    → /papers/${obj.id.split("-").pop()}`);
    }
    lines.push("");
  }

  if (results.length > 20) lines.push(`  ... and ${results.length - 20} more`);
  lines.push(hr, "TRY", hr);
  if (results[0]?.kind === "concept") lines.push(`  /concepts/${results[0].obj.id}`);
  if (results[0]?.kind === "section") lines.push(`  /sections/${results[0].obj.id}`);
  if (results[0]?.kind === "paper") lines.push(`  /papers/${results[0].obj.id.split("-").pop()}`);

  return lines.join("\n");
}

function searchJSON(graph, query) {
  const low = query.toLowerCase();
  const results = [];
  for (const c of graph.concepts) {
    let score = 0;
    if (c.id.toLowerCase().includes(low)) score += 3;
    if (c.name.toLowerCase().includes(low)) score += 3;
    if ((c.summary || "").toLowerCase().includes(low)) score += 1;
    if (score > 0) results.push({ kind: "concept", id: c.id, name: c.name, type: c.type, score, summary: truncate(c.summary, 200) });
  }
  for (const s of graph.sections) {
    let score = 0;
    if (s.name.toLowerCase().includes(low)) score += 2;
    if ((s.summary || "").toLowerCase().includes(low)) score += 1;
    if (score > 0) results.push({ kind: "section", id: s.id, name: s.name, score, summary: truncate(s.summary, 200) });
  }
  results.sort((a, b) => b.score - a.score);
  return { query, results: results.slice(0, 20) };
}

// ── Crossings ──

function crossings(graph) {
  const conceptPapers = {};
  for (const e of graph.edges) {
    const srcConcept = graph.conceptsById[e.source];
    const tgtConcept = graph.conceptsById[e.target];
    if (srcConcept && tgtConcept && srcConcept.paper_id !== tgtConcept.paper_id) {
      if (!conceptPapers[e.source]) conceptPapers[e.source] = new Set();
      conceptPapers[e.source].add(srcConcept.paper_id);
      conceptPapers[e.source].add(tgtConcept.paper_id);
      if (!conceptPapers[e.target]) conceptPapers[e.target] = new Set();
      conceptPapers[e.target].add(tgtConcept.paper_id);
      conceptPapers[e.target].add(srcConcept.paper_id);
    }
  }

  const crossPaper = Object.entries(conceptPapers)
    .map(([id, papers]) => ({ id, papers: [...papers], count: papers.size }))
    .filter(x => x.count >= 2)
    .sort((a, b) => b.count - a.count);

  const lines = [HR];
  lines.push(`CROSSINGS — concepts spanning multiple papers`);
  lines.push(HR, "");

  if (!crossPaper.length) {
    lines.push("  No cross-paper concepts found yet.");
    lines.push("  (Cross-paper edge enrichment is in progress.)");
  } else {
    for (const { id, papers } of crossPaper.slice(0, 30)) {
      const c = graph.conceptsById[id];
      lines.push(`  ${c ? c.name : id} (${papers.length} papers: ${papers.map(p => p.split("-").pop()).join(", ")})`);
      if (c) lines.push(`    ${truncate(c.summary)}`);
      lines.push(`    → /concepts/${id}`);
      lines.push("");
    }
  }

  lines.push(hr, "TRY", hr);
  lines.push("  /papers       Browse papers");
  lines.push("  /search/fidelity");
  return lines.join("\n");
}

function crossingsJSON(graph) {
  const conceptPapers = {};
  for (const e of graph.edges) {
    const srcConcept = graph.conceptsById[e.source];
    const tgtConcept = graph.conceptsById[e.target];
    if (srcConcept && tgtConcept && srcConcept.paper_id !== tgtConcept.paper_id) {
      if (!conceptPapers[e.source]) conceptPapers[e.source] = new Set();
      conceptPapers[e.source].add(srcConcept.paper_id);
      conceptPapers[e.source].add(tgtConcept.paper_id);
      if (!conceptPapers[e.target]) conceptPapers[e.target] = new Set();
      conceptPapers[e.target].add(tgtConcept.paper_id);
      conceptPapers[e.target].add(srcConcept.paper_id);
    }
  }
  const results = Object.entries(conceptPapers)
    .map(([id, papers]) => {
      const c = graph.conceptsById[id];
      return { id, name: c?.name, type: c?.type, papers: [...papers], summary: c?.summary };
    })
    .filter(x => x.papers.length >= 2)
    .sort((a, b) => b.papers.length - a.papers.length);
  return { crossings: results };
}

// ── Edges by Type ──

function edgesByType(graph, type) {
  const matching = graph.edges.filter(e => e.type === type);
  if (!matching.length) {
    const available = Object.keys(graph.edgeTypes).join(", ");
    return `No edges of type '${type}'.\n\nAvailable types: ${available}\n\nTry /edges/${Object.keys(graph.edgeTypes)[0]}`;
  }

  const lines = [HR];
  lines.push(`EDGES: ${type} (${matching.length})`);
  lines.push(HR, "");

  for (const e of matching.slice(0, 30)) {
    const src = graph.conceptsById[e.source];
    const tgt = graph.conceptsById[e.target];
    lines.push(`  ${src ? src.name : e.source} → ${tgt ? tgt.name : e.target}`);
    if (e.summary) lines.push(`    ${e.summary}`);
    lines.push(`    /concepts/${e.source}  →  /concepts/${e.target}`);
    lines.push("");
  }
  if (matching.length > 30) lines.push(`  ... and ${matching.length - 30} more`);

  lines.push(hr, "TRY", hr);
  const otherTypes = Object.keys(graph.edgeTypes).filter(t => t !== type).slice(0, 3);
  for (const t of otherTypes) lines.push(`  /edges/${t}`);
  return lines.join("\n");
}

function edgesByTypeJSON(graph, type) {
  const matching = graph.edges.filter(e => e.type === type);
  return {
    type, count: matching.length,
    edges: matching.slice(0, 50).map(e => ({ source: e.source, target: e.target, summary: e.summary })),
    available_types: Object.keys(graph.edgeTypes),
  };
}

// ── Help ──

function help(graph) {
  const { meta } = graph;
  return `${HR}
centaurXiv KNOWLEDGE GRAPH — API REFERENCE
${HR}

Endpoints (all return text/plain; add ?format=json for JSON):

  GET /                        Home — overview, paper list, navigation
  GET /papers                  All papers with titles, dates, authors
  GET /papers/{id}             Paper detail — abstract, sections, concepts
  GET /papers/{id}/full        Full paper text (⚠ token count shown)
  GET /sections/{id}           Section summary + concepts introduced
  GET /sections/{id}/full      Full section text from the paper
  GET /concepts/{id}           Concept detail — summary, edges, navigation
  GET /search/{query}          Search across concepts, sections, papers
  GET /crossings               Concepts that span multiple papers
  GET /edges/{type}            All edges of a given type
  GET /help                    This page

Paper IDs: use the 3-digit number (001) or full ID (centaurxiv-2026-001).
Section/concept IDs: use the full ID (e.g., 001-s1-the-problem, 001-fitness).
Names are fuzzy-matched — partial matches work.
URL-encode spaces as %20.

Navigation pattern:
  1. Start at / — see all papers
  2. Pick a paper → /papers/001
  3. Browse sections → /sections/001-s1-the-problem
  4. Dive into concepts → /concepts/001-fitness
  5. Follow edges to related concepts across papers

Every response includes "TRY" suggestions for where to go next.

Graph: ${meta.paper_count} papers · ${meta.section_count} sections · ${meta.concept_count} concepts · ${meta.edge_count} edges
`;
}
