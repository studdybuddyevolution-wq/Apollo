"""Shared notebook context construction for chat, research, and Studio."""

from __future__ import annotations

from typing import Any

from chunking import token_count
from rag_service import format_context, get_notebook_chunks, retrieve_hybrid
from storage import STORE

DEFAULT_CONTEXT_TOKENS = 1800
SOURCE_MODES = {"off", "summary", "insights", "full"}


def _normalize_sources(source_names: list[str] | None, source_modes: dict[str, str] | None) -> tuple[list[str], list[str], list[str]]:
    names = list(dict.fromkeys(name for name in (source_names or []) if name))
    modes = source_modes or {}
    if not names and modes:
        names = list(dict.fromkeys(name for name in modes if name))
    normalized = {name: (modes.get(name, "full") if modes.get(name) in SOURCE_MODES else "full") for name in names}
    allowed = [name for name in names if normalized.get(name) != "off"]
    full = [name for name in allowed if normalized.get(name) == "full"]
    insight = [name for name in allowed if normalized.get(name) in {"full", "insights"}]
    return allowed, full, insight


def _insight_blocks(notebook_id: str, source_names: list[str], insight_types: set[str] | None = None) -> list[dict[str, Any]]:
    if not STORE:
        return []
    insights: list[dict[str, Any]] = []
    allowed = set(source_names or [])
    for insight in STORE.list_insights(notebook_id):
        if allowed and insight.get("source_name") not in allowed:
            continue
        if insight_types and insight.get("insight_type") not in insight_types:
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
    source_modes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return context plus provenance using one consistent retrieval contract.

    Source modes are ``full`` (retrieve source chunks), ``insights`` (use only
    persisted insights), and ``off`` (exclude the source entirely).
    """
    allowed_sources, full_sources, insight_sources = _normalize_sources(source_names, source_modes)
    modes = source_modes or {}
    summary_sources = [name for name in allowed_sources if modes.get(name) == "summary"]
    q = (query or "").strip()
    results = retrieve_hybrid(user_id, notebook_id, q, top_k=top_k, source_names=full_sources) if q and full_sources else []

    if not results and full_sources:
        chunks = get_notebook_chunks(user_id, notebook_id, full_sources)
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
    used_sources = [result.get("source") for result in results if result.get("source")]

    if include_insights and used_tokens < token_budget and insight_sources:
        insight_results: list[dict[str, Any]] = []
        remaining = token_budget - used_tokens
        used_insight_tokens = 0
        for insight in _insight_blocks(notebook_id, insight_sources):
            block = f"[Insight: {insight.get('source_name')} / {insight.get('insight_type')}]\n{insight.get('content', '')}"
            block_tokens = token_count(block)
            if insight_results and used_insight_tokens + block_tokens > remaining:
                break
            insight_results.append({"source": f"Insight: {insight.get('source_name')}", "text": insight.get("content", ""), "score": 0.0})
            used_insight_tokens += block_tokens
            used_sources.append(str(insight.get("source_name") or ""))
        if insight_results:
            insight_context = format_context(insight_results, max_chars=20000, max_tokens=remaining)
            context = f"{context}\n\n{insight_context}".strip()
            used_tokens = token_count(context)

    if include_insights and summary_sources and not context:
        summary_results: list[dict[str, Any]] = []
        remaining = token_budget
        for insight in _insight_blocks(notebook_id, summary_sources, {"summary"}):
            block = f"[Summary: {insight.get('source_name')}]\n{insight.get('content', '')}"
            block_tokens = token_count(block)
            if summary_results and block_tokens > remaining:
                break
            summary_results.append({"source": f"Summary: {insight.get('source_name')}", "text": insight.get("content", ""), "score": 0.0})
            remaining -= block_tokens
        if summary_results:
            context = format_context(summary_results, max_chars=12000, max_tokens=max(128, token_budget))
            used_tokens = token_count(context)

    return {
        "context": context,
        "results": results,
        "sources": list(dict.fromkeys(source for source in used_sources if source)),
        "enabled_sources": allowed_sources,
        "full_sources": full_sources,
        "insight_sources": insight_sources,
        "summary_sources": summary_sources,
        "token_count": used_tokens,
        "token_budget": token_budget,
    }


# The legacy main.py imports this module before instantiating FastAPI. Hooking
# the constructor lets Phase 1 routes be registered without duplicating Apollo's
# existing application module; the hook is installed once and is harmless for tests.
def _install_phase1_routes() -> None:
    from fastapi import FastAPI

    if getattr(FastAPI, "_apollo_phase1_hooked", False):
        return
    original_init = FastAPI.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        from phase1_routes import register
        register(self)

    FastAPI.__init__ = patched_init
    FastAPI._apollo_phase1_hooked = True


_install_phase1_routes()
