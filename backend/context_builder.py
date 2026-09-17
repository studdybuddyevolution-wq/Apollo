"""Shared notebook context construction for chat, research, and Studio."""

from __future__ import annotations

from typing import Any

from chunking import token_count
from rag_service import format_context, get_notebook_chunks, retrieve_hybrid
from storage import STORE

DEFAULT_CONTEXT_TOKENS = 1800


def _insight_blocks(notebook_id: str, source_names: list[str]) -> list[dict[str, Any]]:
    if not STORE:
        return []
    insights: list[dict[str, Any]] = []
    allowed = set(source_names or [])
    for insight in STORE.list_insights(notebook_id):
        if allowed and insight.get("source_name") not in allowed:
            continue
        insights.append(insight)
    return insights


def build_context(
    user_id: str | None,
    notebook_id: str,
    source_names: list[str] | None,
    query: str | None,
    token_budget: int = DEFAULT_CONTEXT_TOKENS,
    top_k: int = 8,
    include_insights: bool = False,
) -> dict[str, Any]:
    """Return context plus provenance using one consistent retrieval contract."""
    sources = list(source_names or [])
    q = (query or "").strip()
    results = retrieve_hybrid(user_id, notebook_id, q, top_k=top_k, source_names=sources) if q else []

    if not results:
        chunks = get_notebook_chunks(user_id, notebook_id, sources)
        # Overview mode: preserve source diversity before filling the budget.
        selected: list[dict[str, Any]] = []
        seen_sources: set[str] = set()
        for chunk in chunks:
            source = str(chunk.get("source") or "unknown source")
            if source not in seen_sources:
                selected.append({"source": source, "text": chunk.get("text", ""), "score": 0.0})
                seen_sources.add(source)
            if len(selected) >= top_k:
                break
        results = selected

    context = format_context(results, max_chars=20000, max_tokens=max(128, token_budget))
    used_tokens = token_count(context)

    if include_insights and used_tokens < token_budget:
        insight_results: list[dict[str, Any]] = []
        remaining = token_budget - used_tokens
        used_insight_tokens = 0
        for insight in _insight_blocks(notebook_id, sources):
            block = f"[Insight: {insight.get('source_name')} / {insight.get('insight_type')}]\n{insight.get('content', '')}"
            block_tokens = token_count(block)
            if insight_results and used_insight_tokens + block_tokens > remaining:
                break
            insight_results.append({"source": f"Insight: {insight.get('source_name')}", "text": insight.get("content", ""), "score": 0.0})
            used_insight_tokens += block_tokens
        if insight_results:
            insight_context = format_context(insight_results, max_chars=20000, max_tokens=remaining)
            context = f"{context}\n\n{insight_context}".strip()
            used_tokens = token_count(context)

    return {
        "context": context,
        "results": results,
        "sources": list(dict.fromkeys(result.get("source", "unknown source") for result in results if result.get("source"))),
        "token_count": used_tokens,
        "token_budget": token_budget,
    }
