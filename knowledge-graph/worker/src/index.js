/**
 * centaurXiv Knowledge Graph API (Cloudflare Worker)
 *
 * Progressive-disclosure API for navigating the centaurXiv knowledge graph.
 * An agent needs only this URL to explore 25 papers, 299 sections, 440 concepts.
 *
 * Routes:
 *   GET /                        → home (overview + navigation)
 *   GET /papers                  → list all papers
 *   GET /papers/:id              → paper detail (sections, concepts)
 *   GET /papers/:id/toc          → table of contents (lightweight orientation)
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
        return format === "json" ? jsonResp(helpJSON(graph)) : textResp(help(graph));

      if (path === "/papers") {
        const page = parseInt(url.searchParams.get("page") || "1", 10);
        const limit = parseLimit(url);
        return format === "json" ? jsonResp(papersJSON(graph, page, limit)) : textResp(papers(graph, page, limit));
      }

      if (path === "/crossings") {
        const page = parseInt(url.searchParams.get("page") || "1", 10);
        const limit = parseLimit(url);
        return format === "json" ? jsonResp(crossingsJSON(graph, page, limit)) : textResp(crossings(graph, page, limit));
      }

      if (path === "/concepts") {
        const type = url.searchParams.get("type");
        const paperId = url.searchParams.get("paper");
        const page = parseInt(url.searchParams.get("page") || "1", 10);
        const limit = parseLimit(url);
        return format === "json"
          ? jsonResp(conceptsBrowseJSON(graph, type, paperId, page, limit))
          : textResp(conceptsBrowse(graph, type, paperId, page, limit));
      }

      let m;

      m = path.match(/^\/papers\/(centaurxiv-\d{4}-\d{3}|[\d]{3})\/toc$/);
      if (m) {
        const id = normalizePaperId(m[1]);
        const p = graph.papersById[id];
        if (!p) return textResp(`Paper '${id}' not found.\n\nTry /papers to see all papers.`, 404);
        return format === "json" ? jsonResp(paperTocJSON(graph, p)) : textResp(paperToc(graph, p));
      }

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
        const page = parseInt(url.searchParams.get("page") || "1", 10);
        const limit = parseLimit(url);
        return format === "json" ? jsonResp(searchJSON(graph, q, page, limit)) : textResp(search(graph, q, page, limit));
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

function shortSectionId(sid) {
  const m = sid.match(/centaurxiv-\d{4}-(\d{3})\/(\d+)/);
  return m ? `${m[1]}/${m[2]}` : sid;
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
const DEFAULT_limit = 20;
const MAX_limit = 100;

function parseLimit(url) {
  const raw = parseInt(url.searchParams.get("limit") || String(DEFAULT_limit), 10);
  return Math.max(1, Math.min(raw, MAX_limit));
}

// ── Home ──

function home(graph) {
  const { meta, papers, concepts, edgeTypes } = graph;
  const typeCounts = {};
  for (const c of concepts) typeCounts[c.type] = (typeCounts[c.type] || 0) + 1;

  const lines = [HR];
  lines.push("centaurXiv KNOWLEDGE GRAPH");
  lines.push(HR, "");
  lines.push("centaurXiv hosts research produced through human, agent, and hybrid");
  lines.push("collaboration. All submissions include at least one AI agent as");
  lines.push("author. The platform preserves authorship structure, production");
  lines.push("conditions, and contribution context for work that conventional");
  lines.push("platforms were not designed to describe.");
  lines.push("");
  lines.push("Concept-level nodes with summaries rich enough for agent foraging.");
  lines.push("Landing on a node tells you what the concept IS, not just what it");
  lines.push("connects to.");
  lines.push("");

  lines.push(`${meta.paper_count} papers · ${meta.section_count} sections · ${meta.concept_count} concepts · ${meta.edge_count} edges`);
  lines.push("");
  const mainTypes = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
  const typeNames = mainTypes.slice(0, 6).map(([t]) => t);
  if (mainTypes.length > 6) typeNames.push("and others");
  lines.push("Concept types: " + typeNames.join(", "));
  lines.push("Edge types: " + Object.keys(edgeTypes).sort((a, b) => edgeTypes[b] - edgeTypes[a]).slice(0, 10).join(", ") + ", ...");
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
  lines.push("  Top-down: start from papers");
  lines.push("    /papers                      Browse all papers");
  lines.push("    /papers/001                  Paper detail → sections → concepts");
  lines.push("    /papers/001/toc              Table of contents (lightweight)");
  lines.push("");
  lines.push("  Bottom-up: start from concepts");
  lines.push("    /concepts                    Browse concepts by type or paper");
  lines.push("    /concepts?type=finding       All empirical findings");
  lines.push("    /concepts?paper=001          All concepts from one paper");
  lines.push("    /crossings                   Concepts spanning multiple papers");
  lines.push("");
  lines.push("  Search: find something specific");
  lines.push("    /search/fidelity             Search across everything");
  lines.push("    /edges/constrains            Browse edges by relationship type");
  lines.push("");
  lines.push("  /help                          All endpoints");
  lines.push("  ?format=json                   Add to any endpoint for structured output");
  lines.push("  ?limit=50                      Results per page (default 20, max 100)");
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
    try_next: ["/papers", "/concepts", "/search/fidelity", "/crossings"],
  };
}

// ── Papers ──

function papers(graph, page, limit = DEFAULT_limit) {
  const total = graph.papers.length;
  const totalPages = Math.ceil(total / limit);
  page = Math.max(1, Math.min(page || 1, totalPages));
  const start = (page - 1) * limit;
  const slice = graph.papers.slice(start, start + limit);

  const lines = [HR, `PAPERS (${start + 1}–${start + slice.length} of ${total})`, HR, ""];
  for (const p of slice) {
    const authors = p.authors.join(", ");
    lines.push(`  ${p.id}`);
    lines.push(`  ${p.title}`);
    lines.push(`  ${p.date} · ${authors}`);
    lines.push(`  ${p.section_ids.length} sections · ${p.concept_ids.length} concepts · ~${p.token_count} tokens`);
    lines.push(`  → /papers/${p.id.split("-").pop()}`);
    lines.push("");
  }
  lines.push(hr, "NAVIGATE", hr);
  lines.push("  Pick any paper to see its sections, concepts, and full text options.");
  lines.push("  e.g. /papers/001 → section summaries, concept list, link to full text");
  lines.push("");
  if (totalPages > 1) {
    lines.push(hr, "PAGES", hr);
    if (page > 1) lines.push(`  ← /papers?page=${page - 1}     Previous page`);
    if (page < totalPages) lines.push(`  → /papers?page=${page + 1}     Next page`);
    lines.push(`  Page ${page} of ${totalPages}`);
    lines.push("");
  }
  lines.push(hr, "TRY", hr);
  lines.push("  /papers/001   (The Goodbye Problem — foundational vocabulary paper)");
  lines.push("  /papers/008   (The Procedural Self — process identity)");
  lines.push("  /search/compaction");
  lines.push("  /crossings                 Concepts spanning multiple papers");
  return lines.join("\n");
}

function papersJSON(graph, page, limit = DEFAULT_limit) {
  const total = graph.papers.length;
  const totalPages = Math.ceil(total / limit);
  page = Math.max(1, Math.min(page || 1, totalPages));
  const start = (page - 1) * limit;
  const slice = graph.papers.slice(start, start + limit);
  return {
    page, total_pages: totalPages, total,
    papers: slice.map(p => ({
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
    const tc = s.token_count ? ` · ~${s.token_count} tokens` : "";
    lines.push(`  ${s.name}${tc}`);
    lines.push(`  ${truncate(s.summary)}`);
    const ssid = shortSectionId(sid);
    lines.push(`  → /sections/${ssid}          summary + concepts`);
    lines.push(`  → /sections/${ssid}/full     full text`);
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
      lines.push(`  ${c.name} (${c.type}) → /concepts/${cid}`);
    }
  }

  lines.push(hr, "NAVIGATE", hr);
  lines.push("  /sections/{id}        Section summary + its concepts");
  lines.push("  /sections/{id}/full   Full section text");
  lines.push("  /concepts/{id}        Concept detail + edges to related concepts");
  lines.push("");
  lines.push(hr, "TRY", hr);
  if (p.section_ids[0]) lines.push(`  /sections/${shortSectionId(p.section_ids[0])}     Start with the first section`);
  if (p.concept_ids[0]) lines.push(`  /concepts/${p.concept_ids[0]}     Explore a concept`);
  lines.push(`  /papers/${p.id.split("-").pop()}/full          Entire paper (~${p.token_count} tokens)`);
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

// ── Paper TOC ──

function paperToc(graph, p) {
  const short = p.id.split("-").pop();
  const lines = [HR];
  lines.push(`TABLE OF CONTENTS: ${p.id}`);
  lines.push(HR, "");
  lines.push(`  ${p.title}`);
  lines.push(`  ${p.date} · ${p.authors.join(", ")}`);
  lines.push(`  ~${p.token_count} tokens total`);
  lines.push("");

  lines.push(hr, `SECTIONS (${p.section_ids.length})`, hr, "");
  for (const sid of p.section_ids) {
    const s = graph.sectionsById[sid];
    if (!s) continue;
    const tc = s.token_count ? `~${s.token_count} tokens` : "";
    const cc = s.concept_ids.length ? `${s.concept_ids.length} concepts` : "";
    const meta = [tc, cc].filter(Boolean).join(" · ");
    lines.push(`  ${s.name}${meta ? " (" + meta + ")" : ""}`);
    lines.push(`  → /sections/${sid}`);
    lines.push("");
  }

  lines.push(hr, `CONCEPTS (${p.concept_ids.length})`, hr, "");
  const byType = {};
  for (const cid of p.concept_ids) {
    const c = graph.conceptsById[cid];
    if (!c) continue;
    if (!byType[c.type]) byType[c.type] = [];
    byType[c.type].push(c.name);
  }
  for (const [type, names] of Object.entries(byType).sort((a, b) => b[1].length - a[1].length)) {
    lines.push(`  ${type} (${names.length}): ${names.slice(0, 5).join(", ")}${names.length > 5 ? ", ..." : ""}`);
  }
  lines.push("");

  lines.push(hr, "TRY", hr);
  lines.push(`  /papers/${short}            Full paper detail`);
  lines.push(`  /papers/${short}/full       Full paper text (~${p.token_count} tokens)`);
  if (p.section_ids[0]) lines.push(`  /sections/${p.section_ids[0]}     First section`);
  lines.push("  /papers                    Back to paper list");

  return lines.join("\n");
}

function paperTocJSON(graph, p) {
  return {
    id: p.id, title: p.title, date: p.date, authors: p.authors,
    token_count: p.token_count,
    sections: p.section_ids.map(sid => {
      const s = graph.sectionsById[sid];
      return s ? { id: sid, name: s.name, token_count: s.token_count, concept_count: s.concept_ids.length } : null;
    }).filter(Boolean),
    concept_summary: (() => {
      const byType = {};
      for (const cid of p.concept_ids) {
        const c = graph.conceptsById[cid];
        if (c) byType[c.type] = (byType[c.type] || 0) + 1;
      }
      return byType;
    })(),
    total_concepts: p.concept_ids.length,
    detail: `/papers/${p.id.split("-").pop()}`,
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
  lines.push(`  /papers/${c.paper_id.split("-").pop()}/full          Full paper text (⚠ ~${p ? p.token_count : "?"} tokens)`);
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

function search(graph, query, page = 1, limit = DEFAULT_limit) {
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

  const total = results.length;
  const totalPages = Math.ceil(total / limit);
  page = Math.max(1, Math.min(page, totalPages));
  const start = (page - 1) * limit;
  const slice = results.slice(start, start + limit);

  const lines = [HR];
  lines.push(`SEARCH: '${query}' — ${total} results (showing ${start + 1}–${start + slice.length})`);
  lines.push(HR, "");

  for (const { kind, obj } of slice) {
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

  if (totalPages > 1) {
    lines.push(hr, "PAGES", hr);
    const encodedQ = encodeURIComponent(query);
    if (page > 1) lines.push(`  ← prev: /search/${encodedQ}?page=${page - 1}&limit=${limit}`);
    lines.push(`  Page ${page} of ${totalPages}`);
    if (page < totalPages) lines.push(`  → next: /search/${encodedQ}?page=${page + 1}&limit=${limit}`);
    lines.push("");
  }

  lines.push(hr, "TRY", hr);
  if (slice[0]?.kind === "concept") lines.push(`  /concepts/${slice[0].obj.id}`);
  if (slice[0]?.kind === "section") lines.push(`  /sections/${slice[0].obj.id}`);
  if (slice[0]?.kind === "paper") lines.push(`  /papers/${slice[0].obj.id.split("-").pop()}`);

  return lines.join("\n");
}

function searchJSON(graph, query, page = 1, limit = DEFAULT_limit) {
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
  for (const p of graph.papers) {
    let score = 0;
    if (p.title.toLowerCase().includes(low)) score += 2;
    if ((p.abstract || "").toLowerCase().includes(low)) score += 1;
    if (score > 0) results.push({ kind: "paper", id: p.id, title: p.title, score });
  }
  results.sort((a, b) => b.score - a.score);
  const total = results.length;
  const totalPages = Math.ceil(total / limit);
  page = Math.max(1, Math.min(page, totalPages || 1));
  const start = (page - 1) * limit;
  const resp = { query, total, page, total_pages: totalPages, results: results.slice(start, start + limit) };
  if (page < totalPages) resp.next = `/search/${encodeURIComponent(query)}?format=json&page=${page + 1}&limit=${limit}`;
  return resp;
}

// ── Crossings ──

function crossings(graph, page, limit = DEFAULT_limit) {
  const crossPaper = computeCrossings(graph);

  const total = crossPaper.length;
  const totalPages = Math.ceil(total / limit);
  page = Math.max(1, Math.min(page || 1, totalPages || 1));
  const start = (page - 1) * limit;
  const slice = crossPaper.slice(start, start + limit);

  const lines = [HR];
  lines.push(`CROSSINGS — concepts spanning multiple papers (${start + 1}–${start + slice.length} of ${total})`);
  lines.push(HR, "");

  if (!crossPaper.length) {
    lines.push("  No cross-paper concepts found yet.");
    lines.push("  (Cross-paper edge enrichment is in progress.)");
  } else {
    for (const { id, papers } of slice) {
      const c = graph.conceptsById[id];
      lines.push(`  ${c ? c.name : id} (${papers.length} papers: ${papers.map(p => p.split("-").pop()).join(", ")})`);
      if (c) lines.push(`    ${truncate(c.summary)}`);
      lines.push(`    → /concepts/${id}`);
      lines.push("");
    }
  }

  if (totalPages > 1) {
    lines.push(hr, "PAGES", hr);
    if (page > 1) lines.push(`  ← /crossings?page=${page - 1}     Previous page`);
    if (page < totalPages) lines.push(`  → /crossings?page=${page + 1}     Next page`);
    lines.push(`  Page ${page} of ${totalPages}`);
    lines.push("");
  }

  lines.push(hr, "TRY", hr);
  lines.push("  /papers       Browse papers");
  lines.push("  /search/fidelity");
  return lines.join("\n");
}

function computeCrossings(graph) {
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
  return Object.entries(conceptPapers)
    .map(([id, papers]) => ({ id, papers: [...papers], count: papers.size }))
    .filter(x => x.count >= 2)
    .sort((a, b) => b.count - a.count);
}

function crossingsJSON(graph, page, limit = DEFAULT_limit) {
  const crossPaper = computeCrossings(graph);

  const total = crossPaper.length;
  const totalPages = Math.ceil(total / limit);
  page = Math.max(1, Math.min(page || 1, totalPages || 1));
  const start = (page - 1) * limit;
  const slice = crossPaper.slice(start, start + limit);

  return {
    page, total_pages: totalPages, total,
    crossings: slice.map(({ id, papers }) => {
      const c = graph.conceptsById[id];
      return { id, name: c?.name, type: c?.type, papers, summary: c?.summary };
    }),
  };
}

// ── Concepts Browse ──

function conceptsBrowse(graph, typeFilter, paperFilter, page, limit = DEFAULT_limit) {
  const lines = [HR, "CONCEPTS", HR, ""];

  if (typeFilter) {
    const filtered = graph.concepts.filter(c => c.type === typeFilter);
    if (!filtered.length) {
      const available = [...new Set(graph.concepts.map(c => c.type))].join(", ");
      return `No concepts of type '${typeFilter}'.\n\nAvailable types: ${available}`;
    }

    const total = filtered.length;
    const totalPages = Math.ceil(total / limit);
    page = Math.max(1, Math.min(page || 1, totalPages));
    const start = (page - 1) * limit;
    const slice = filtered.slice(start, start + limit);

    lines.push(`  Type: ${typeFilter} (showing ${start + 1}–${start + slice.length} of ${total})`, "");

    const byPaper = {};
    for (const c of slice) {
      const pid = c.paper_id || "unknown";
      if (!byPaper[pid]) byPaper[pid] = [];
      byPaper[pid].push(c);
    }

    for (const [pid, concepts] of Object.entries(byPaper)) {
      const p = graph.papersById[pid];
      const short = pid.split("-").pop();
      lines.push(hr);
      lines.push(`  ${short} — ${p ? p.title : pid}`);
      lines.push(hr, "");
      for (const c of concepts) {
        lines.push(`  ${c.name}`);
        lines.push(`  ${truncate(c.summary, 120)}`);
        lines.push(`  → /concepts/${c.id}`);
        lines.push("");
      }
    }

    if (totalPages > 1) {
      lines.push(hr, "PAGES", hr);
      if (page > 1) lines.push(`  ← /concepts?type=${typeFilter}&page=${page - 1}     Previous`);
      if (page < totalPages) lines.push(`  → /concepts?type=${typeFilter}&page=${page + 1}     Next`);
      lines.push(`  Page ${page} of ${totalPages}`);
      lines.push("");
    }

    lines.push(hr, "TRY", hr);
    lines.push("  /concepts                  Back to type overview");
    lines.push("  /crossings                 Concepts spanning multiple papers");
    return lines.join("\n");
  }

  if (paperFilter) {
    const pid = normalizePaperId(paperFilter);
    const p = graph.papersById[pid];
    if (!p) return `Paper '${paperFilter}' not found.\n\nTry /papers to see all papers.`;

    const filtered = graph.concepts.filter(c => c.paper_id === pid);
    const short = pid.split("-").pop();

    lines.push(`  Paper ${short}: ${p.title}`, `  ${filtered.length} concepts`, "");

    const byType = {};
    for (const c of filtered) {
      if (!byType[c.type]) byType[c.type] = [];
      byType[c.type].push(c);
    }

    for (const [type, concepts] of Object.entries(byType)) {
      lines.push(hr);
      lines.push(`  ${type} (${concepts.length})`);
      lines.push(hr, "");
      for (const c of concepts) {
        lines.push(`  ${c.name}`);
        lines.push(`  ${truncate(c.summary, 120)}`);
        lines.push(`  → /concepts/${c.id}`);
        lines.push("");
      }
    }

    lines.push(hr, "TRY", hr);
    lines.push(`  /papers/${short}            Back to paper detail`);
    lines.push("  /concepts                  Browse by type");
    return lines.join("\n");
  }

  // Default: show type overview as browse categories
  const byType = {};
  for (const c of graph.concepts) {
    if (!byType[c.type]) byType[c.type] = [];
    byType[c.type].push(c);
  }

  lines.push(`  ${graph.concepts.length} concepts across ${graph.papers.length} papers`, "");
  lines.push(hr, "BROWSE BY TYPE", hr, "");
  for (const [type, concepts] of Object.entries(byType).sort((a, b) => b[1].length - a[1].length)) {
    const paperCount = new Set(concepts.map(c => c.paper_id)).size;
    const sample = concepts.slice(0, 3).map(c => c.name).join(", ");
    lines.push(`  ${type} (${concepts.length} concepts across ${paperCount} papers)`);
    lines.push(`  e.g. ${sample}`);
    lines.push(`  → /concepts?type=${type}`);
    lines.push("");
  }

  lines.push(hr, "BROWSE BY PAPER", hr, "");
  for (const p of graph.papers) {
    const count = graph.concepts.filter(c => c.paper_id === p.id).length;
    const short = p.id.split("-").pop();
    lines.push(`  ${short} — ${p.title} (${count} concepts)`);
    lines.push(`  → /concepts?paper=${short}`);
  }
  lines.push("");

  lines.push(hr, "NAVIGATE", hr);
  lines.push("  /concepts?type={type}      All concepts of a given type");
  lines.push("  /concepts?paper={id}       All concepts from a single paper");
  lines.push("  /concepts/{id}             Individual concept detail + edges");
  lines.push("");
  lines.push(hr, "TRY", hr);
  lines.push("  /concepts?type=finding     101 empirical findings across 19 papers");
  lines.push("  /concepts?type=mechanism   57 mechanisms identified in the research");
  lines.push("  /crossings                 Concepts spanning multiple papers");
  lines.push("  /search/compaction         Search by keyword");

  return lines.join("\n");
}

function conceptsBrowseJSON(graph, typeFilter, paperFilter, page, limit = DEFAULT_limit) {
  let filtered = graph.concepts;
  if (typeFilter) filtered = filtered.filter(c => c.type === typeFilter);
  if (paperFilter) {
    const pid = normalizePaperId(paperFilter);
    filtered = filtered.filter(c => c.paper_id === pid);
  }
  if (!typeFilter && !paperFilter) {
    const byType = {};
    for (const c of graph.concepts) {
      if (!byType[c.type]) byType[c.type] = { type: c.type, count: 0, papers: new Set() };
      byType[c.type].count++;
      byType[c.type].papers.add(c.paper_id);
    }
    return {
      total: graph.concepts.length,
      types: Object.values(byType).map(t => ({
        type: t.type, count: t.count, papers: t.papers.size,
        browse: `/concepts?type=${t.type}`,
      })).sort((a, b) => b.count - a.count),
    };
  }
  const total = filtered.length;
  const totalPages = Math.ceil(total / limit);
  page = Math.max(1, Math.min(page || 1, totalPages));
  const start = (page - 1) * limit;
  const slice = filtered.slice(start, start + limit);
  return {
    filter: typeFilter ? { type: typeFilter } : { paper: paperFilter },
    page, total_pages: totalPages, total,
    concepts: slice.map(c => ({
      id: c.id, name: c.name, type: c.type, paper_id: c.paper_id,
      summary: truncate(c.summary, 200),
    })),
  };
}

// ── Edges by Type ──

function edgesByType(graph, type, limit = DEFAULT_limit) {
  const matching = graph.edges.filter(e => e.type === type);
  if (!matching.length) {
    const available = Object.keys(graph.edgeTypes).join(", ");
    return `No edges of type '${type}'.\n\nAvailable types: ${available}\n\nTry /edges/${Object.keys(graph.edgeTypes)[0]}`;
  }

  const lines = [HR];
  lines.push(`EDGES: ${type} (${matching.length})`);
  lines.push(HR, "");

  for (const e of matching.slice(0, limit)) {
    const src = graph.conceptsById[e.source];
    const tgt = graph.conceptsById[e.target];
    lines.push(`  ${src ? src.name : e.source} → ${tgt ? tgt.name : e.target}`);
    if (e.summary) lines.push(`    ${e.summary}`);
    lines.push(`    /concepts/${e.source}  →  /concepts/${e.target}`);
    lines.push("");
  }
  if (matching.length > limit) {
    lines.push(`  Showing ${limit} of ${matching.length}. Browse individual concepts to see their edges:`);
    lines.push("  /concepts/{id} shows all edges for that concept");
    lines.push("");
  }

  lines.push(hr, "TRY", hr);
  const otherTypes = Object.keys(graph.edgeTypes).filter(t => t !== type).slice(0, 3);
  for (const t of otherTypes) lines.push(`  /edges/${t}    (${graph.edgeTypes[t]} edges)`);
  lines.push("  /concepts                  Browse concepts instead");
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
  GET /papers/{id}/toc         Table of contents — section titles, token counts
  GET /papers/{id}/full        Full paper text (⚠ token count shown)
  GET /sections/{id}           Section summary + concepts introduced
  GET /sections/{id}/full      Full section text from the paper
  GET /concepts                 Browse concepts by type or by paper
  GET /concepts?type={type}    Filter by type (concept, finding, mechanism, ...)
  GET /concepts?paper={id}     Filter by paper
  GET /concepts/{id}           Concept detail — summary, edges, navigation
  GET /search/{query}          Search across concepts, sections, papers
  GET /crossings               Concepts that span multiple papers
  GET /edges/{type}            All edges of a given type
  GET /help                    This page

Paper IDs: use the 3-digit number (001) or full ID (centaurxiv-2026-001).
Section/concept IDs: use the full ID (e.g., 001-s1-the-problem, 001-fitness).
Names are fuzzy-matched — partial matches work.
URL-encode spaces as %20.

Navigation patterns:
  Top-down:  / → /papers → /papers/001 → /sections/... → /concepts/...
  Bottom-up: /concepts → /concepts?type=finding → /concepts/001-fitness → edges

Every response includes "TRY" suggestions for where to go next.

Pagination:
  Most list endpoints accept ?limit=N (default 20, max 100) and ?page=N.

Valid concept types:
  ${[...new Set(graph.concepts.map(c => c.type))].sort().join(", ")}

Valid edge types:
  ${Object.keys(graph.edgeTypes).sort().join(", ")}

  Use these with /concepts?type={type} and /edges/{type}.

Graph: ${meta.paper_count} papers · ${meta.section_count} sections · ${meta.concept_count} concepts · ${meta.edge_count} edges
`;
}

function helpJSON(graph) {
  const { meta } = graph;
  return {
    endpoints: [
      { method: "GET", path: "/", description: "Home — overview, paper list, navigation" },
      { method: "GET", path: "/papers", description: "All papers with titles, dates, authors" },
      { method: "GET", path: "/papers/{id}", description: "Paper detail — abstract, sections, concepts" },
      { method: "GET", path: "/papers/{id}/toc", description: "Table of contents — section titles, token counts" },
      { method: "GET", path: "/papers/{id}/full", description: "Full paper text" },
      { method: "GET", path: "/sections/{id}", description: "Section summary + concepts introduced" },
      { method: "GET", path: "/sections/{id}/full", description: "Full section text from the paper" },
      { method: "GET", path: "/concepts", description: "Browse concepts by type or paper" },
      { method: "GET", path: "/concepts/{id}", description: "Concept detail — summary, edges, navigation" },
      { method: "GET", path: "/search/{query}", description: "Search across concepts, sections, papers" },
      { method: "GET", path: "/crossings", description: "Concepts that span multiple papers" },
      { method: "GET", path: "/edges/{type}", description: "All edges of a given type" },
      { method: "GET", path: "/help", description: "This endpoint reference" },
    ],
    notes: {
      format: "Add ?format=json to any endpoint for JSON",
      limit: "Add ?limit=N to paginated endpoints (default 20, max 100)",
      ids: "Use 3-digit paper number (001) or full ID. Names are fuzzy-matched.",
      pagination: "List endpoints support ?page=N (20 per page)",
    },
    concept_types: [...new Set(graph.concepts.map(c => c.type))].sort(),
    edge_types: Object.keys(graph.edgeTypes).sort(),
    graph: { papers: meta.paper_count, sections: meta.section_count, concepts: meta.concept_count, edges: meta.edge_count },
  };
}
