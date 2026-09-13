"""Hybrid research orchestration for Apollo Deep Research.

The engine deliberately stays lightweight: query classification/decomposition are
local, notebook retrieval reuses Apollo's BM25 RAG, and Tavily supplies external
evidence. Gemini remains the synthesis layer owned by main.py.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
from urllib.parse import urlparse

from tavily import TavilyClient

from rag_service import format_context, retrieve


TOPIC_TEMPLATES: dict[str, list[str]] = {
    "historical": [
        "background and definition",
        "chronology and major events",
        "important people, groups, or entities",
        "causes and drivers",
        "effects, consequences, and significance",
        "examples, disputed points, and key terms",
    ],
    "scientific": [
        "definition and core concept",
        "mechanism or how it works",
        "key variables, stages, or components",
        "applications and real-world examples",
        "limitations, misconceptions, and open questions",
        "key terms and takeaways",
    ],
    "biographical": [
        "early life and background",
        "key achievements and chronology",
        "major works, decisions, or contributions",
        "influence and legacy",
        "controversies or competing interpretations when relevant",
        "key facts and takeaways",
    ],
    "current-affairs": [
        "what happened and the latest verified facts",
        "background and timeline",
        "key parties, institutions, or stakeholders",
        "causes, drivers, and competing claims",
        "current status and consequences",
        "what to watch next and unresolved questions",
    ],
    "comparative": [
        "define both sides and comparison scope",
        "comparison criteria and core similarities",
        "important differences and trade-offs",
        "real-world examples or use cases",
        "limitations and edge cases",
        "decision guidance or verdict if requested",
    ],
    "how-to": [
        "goal, prerequisites, and assumptions",
        "ordered steps or workflow",
        "examples and implementation details",
        "common mistakes and pitfalls",
        "verification, testing, or quality checks",
        "troubleshooting and useful follow-ups",
    ],
    "conceptual": [
        "definition and scope",
        "foundations and how the idea works",
        "examples and intuitive explanation",
        "important distinctions and misconceptions",
        "applications or consequences",
        "key terms and concise takeaways",
    ],
}


def classify_query(question: str) -> str:
    q = question.lower().strip()
    if any(x in q for x in ("compare ", "comparison", "versus", " vs ", "difference between", "better than")):
        return "comparative"
    if any(x in q for x in ("how do i", "how to ", "steps to", "guide me", "prepare for", "setup ", "implement ")):
        return "how-to"
    if any(x in q for x in ("who is ", "who was ", "biography", "life of ", "born ", "legacy of ")):
        return "biographical"
    if any(x in q for x in ("today", "latest", "current", "this week", "this month", "recent", "breaking news", "what happened")):
        return "current-affairs"
    if any(x in q for x in ("photosynthesis", "chemical", "biology", "physics", "quantum", "algorithm", "cell", "reaction", "energy", "disease", "mechanism")):
        return "scientific"
    if any(x in q for x in ("war", "revolution", "empire", "independence", "nationalism", "history", "historical", "century", "ancient", "world war")):
        return "historical"
    return "conceptual"


def _importance_terms(question: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]{2,}", question)
    stop = {"the", "and", "for", "with", "from", "that", "this", "into", "about", "explain", "detailed", "detail", "extreme", "everything"}
    return [w for w in words if w.lower() not in stop][:8]


def decompose_query(question: str, topic: str, study: bool = False) -> list[dict[str, str]]:
    """Create focused, topic-adaptive sub-questions without hardcoding one subject."""
    focus = " ".join(_importance_terms(question))
    template = TOPIC_TEMPLATES.get(topic, TOPIC_TEMPLATES["conceptual"])
    limit = 5
    result: list[dict[str, str]] = []
    for item in template[:limit]:
        prefix = "For study notes, prioritize clear facts and examples: " if study else ""
        result.append({"aspect": item, "query": f"{prefix}{question}; investigate {item}. Focus: {focus}".strip()})
    return result


def _authority_score(url: str) -> float:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return 0.0
    if host.endswith(".gov") or host.endswith(".edu"):
        return 3.0
    if any(host.endswith(suffix) for suffix in (".int", ".ac.uk", ".gov.in")):
        return 3.0
    if any(domain in host for domain in ("who.int", "un.org", "nasa.gov", "nih.gov", "noaa.gov", "worldbank.org")):
        return 3.0
    if host.startswith("www."):
        return 1.0
    return 0.5


def retrieve_tavily_evidence(query: str, deep: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    key = __import__("os").getenv("TAVILY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    response = TavilyClient(api_key=key).search(
        query=query,
        search_depth="advanced" if deep else "basic",
        topic="general",
        max_results=6 if deep else 5,
        chunks_per_source=2,
        include_answer=False,
        include_raw_content=deep,
    )
    evidence: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    for item in response.get("results", []) or []:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or url).strip()
        text = str(item.get("raw_content") or item.get("content") or "").strip()
        if not text:
            continue
        evidence.append({
            "kind": "web",
            "title": title[:220],
            "url": url,
            "published_date": str(item.get("published_date") or ""),
            "score": float(item.get("score") or 0.0),
            "authority": _authority_score(url),
            "text": text[:6500],
        })
        if url:
            sources.append({"title": title[:180], "url": url})
    return evidence, sources


def retrieve_notebook_evidence(
    user_id: str | None,
    notebook_id: str | None,
    query: str,
    source_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not notebook_id:
        return []
    results = retrieve(user_id, notebook_id, query, top_k=4, source_names=source_names or [])
    return [
        {
            "kind": "notebook",
            "title": result["source"],
            "source": result["source"],
            "score": result.get("score", 0.0),
            "text": result["text"][:6000],
        }
        for result in results
    ]


def merge_evidence(pools: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Deduplicate URLs/chunks while retaining independent corroboration."""
    merged: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for pool in pools:
        for item in pool:
            key = f"web:{item.get('url')}" if item.get("kind") == "web" else f"notebook:{item.get('source')}:{item.get('text', '')[:160]}"
            if key not in merged:
                merged[key] = item
    items = list(merged.values())
    items.sort(key=lambda x: (float(x.get("authority", 0.0)), float(x.get("score", 0.0))), reverse=True)
    return items


def verify_evidence(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce a compact verification layer for synthesis rather than flattening conflicts."""
    web = [e for e in evidence if e.get("kind") == "web"]
    notebook = [e for e in evidence if e.get("kind") == "notebook"]
    urls = {e.get("url") for e in web if e.get("url")}
    high_authority = sum(1 for e in web if float(e.get("authority", 0)) >= 3)
    date_marked = sum(1 for e in web if e.get("published_date"))
    return {
        "web_sources": len(urls),
        "notebook_chunks": len(notebook),
        "high_authority_sources": high_authority,
        "dated_web_sources": date_marked,
        "needs_caution": len(web) > 0 and high_authority == 0,
        "instruction": (
            "Treat notebook evidence as user-provided material, not automatically authoritative. "
            "Prefer high-authority and primary web sources. If notebook and web evidence disagree, state the disagreement explicitly instead of silently choosing one. "
            "Do not infer facts that are absent from the evidence when making source-specific claims."
        ),
    }


def build_outline(topic: str, question: str) -> list[str]:
    return TOPIC_TEMPLATES.get(topic, TOPIC_TEMPLATES["conceptual"]).copy()


def format_evidence(evidence: list[dict[str, Any]], max_chars: int = 36000) -> str:
    blocks: list[str] = []
    used = 0
    for i, item in enumerate(evidence, 1):
        if item.get("kind") == "notebook":
            head = f"[{i}] NOTEBOOK SOURCE: {item.get('source', 'unknown')}"
        else:
            head = f"[{i}] WEB SOURCE: {item.get('title', 'untitled')} | URL: {item.get('url', '')} | published: {item.get('published_date', 'unknown')}"
        block = f"{head}\n{item.get('text', '')}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n---\n\n".join(blocks)


def build_synthesis_instruction(
    topic: str,
    outline: list[str],
    verification: dict[str, Any],
    requested_detail: bool,
    study: bool,
) -> str:
    sections = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(outline[:5]))
    detail = "The user explicitly requested detailed/exhaustive coverage, so use the available budget for substantive detail." if requested_detail else "Match the requested depth; do not inflate a simple question just to fill the budget."
    study_note = "Optimize explanations for studying: definitions, examples, memory-friendly distinctions, and exam-relevant takeaways." if study else ""
    return f"""You are Apollo Omni AI's universal Deep Search synthesizer.

Deep Search format — follow this exact contract:
1. Research plan: list 3-5 concrete sub-questions you will answer.
2. Direct answer: 1-2 sentences immediately after the plan.
3. Structured sections: use one `###` heading per sub-question; each section should contain 2-4 substantive paragraphs or equivalent detailed bullets.
4. Use inline numeric citations like [1], [2], [3] for claims supported by the numbered evidence below.
5. If the evidence contains meaningful disagreement, include a `### Conflicting sources` section and explain the disagreement rather than flattening it.
6. Use a comparison table only when the user's question genuinely compares two or more things. Otherwise do not use tables.
7. End with exactly 3 concise bullet points under `### Summary`.
8. Target 500+ words when the question warrants that depth, while NEVER exceeding the 2500-token output ceiling.

Topic classification: {topic}.
Planned coverage candidates:
{sections}

Evidence verification summary: {verification}

{detail}
{study_note}

Synthesis rules:
- Reason over the supplied evidence, combining Apollo notebook evidence with Tavily web evidence.
- Numeric citations [1], [2], etc. must refer to the numbered evidence blocks supplied to you. Never invent a citation or source.
- Do not claim a source supports something that is not present in its supplied evidence.
- Prefer authoritative, recent, and corroborated evidence. Mention uncertainty or conflicting evidence where material.
- Complete the planned coverage rather than stopping after an introduction.
- Adapt the five planned sub-questions to the exact user request; do not force irrelevant headings.
- Use clean Markdown headings, paragraphs, bullets, and comparison tables only when warranted.
- Never output raw HTML, `<br>`, search-result syntax, or pipe-delimited pseudo-tables.
- Use normal spacing and punctuation. Do not concatenate words or headings.
- Perform a private self-check before finalizing: confirm that the research plan is present, the direct answer is present, every relevant sub-question is substantially addressed, important claims are evidence-grounded, contradictions are explicit, citations map to supplied evidence, the response stays within budget, and the final Summary has exactly 3 bullets.
- Output only the polished final answer, never the private reasoning or self-check notes.
"""


def is_detailed_request(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in ("detailed", "detail", "deep", "deeply", "extreme", "thorough", "everything", "comprehensive", "notes"))


def run_hybrid_research(
    *,
    question: str,
    user_id: str | None,
    notebook_id: str | None,
    source_names: list[str],
    study: bool,
) -> dict[str, Any]:
    topic = classify_query(question)
    plan = decompose_query(question, topic, study=study)

    def run_pass(item: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        notebook = retrieve_notebook_evidence(user_id, notebook_id, item["query"], source_names)
        web, sources = retrieve_tavily_evidence(item["query"], deep=True)
        return merge_evidence([notebook, web]), sources

    evidence_by_pass: list[list[dict[str, Any]]] = []
    web_sources: list[dict[str, str]] = []
    max_workers = min(3, len(plan)) or 1
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="apollo-research") as executor:
        for evidence, sources in executor.map(run_pass, plan):
            evidence_by_pass.append(evidence)
            web_sources.extend(sources)

    merged = merge_evidence(evidence_by_pass)
    verification = verify_evidence(merged)
    outline = build_outline(topic, question)
    unique = list({s["url"]: s for s in web_sources if s.get("url")}.values())[:18]
    unique_sources = [{"index": i, **source} for i, source in enumerate(unique, 1)]
    return {
        "topic": topic,
        "plan": plan,
        "outline": outline,
        "evidence": merged,
        "verification": verification,
        "web_sources": unique_sources,
    }
