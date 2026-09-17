"""Reusable token-budgeted notebook context construction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chunking import token_count
from rag_service import get_notebook_chunks, retrieve_hybrid
from storage import STORE


@dataclass
class ContextResult:
    text: str
    sources: list[str]
    chunks: list[dict[str, Any]]
    insights: list[dict[str, Any]]


def _fit_blocks(blocks: list[str], token_budget: int) -> str:
    used = 0
    kept: list[str] = []
    for block in blocks:
        tokens = token_count(block)
        if kept and used + tokens > token_budget:
            break
        if not kept and tokens > token_budget:
            kept.append(block)
            break
        kept.append(block)
        used += tokens
    return "\n\n".join(kept)


def _insights(notebook_id: str, source_names: list[str]) -> list[dict[str, Any]]:
    if not STORE:
        return []
    return STORE.list_insights(notebook_id, source_names or None)


def build_context(
    user_id: str | None,
    notebook_id: str,
    source_names: list[str] | None = None,
    query: str | None = None,
    token_budget: int = 1800,
    top_k: int = 8,
    include_insights: bool = True,
) -> ContextResult:
    allowed = list(dict.fromkeys(source_names or []))
    results: list[dict[str, Any]]
    if query and query.strip():
        results = retrieve_hybrid(user_id, notebook_id, query.strip(), top_k=top_k, source_names=allowed)
    else:
        results = []

    if not results:
        raw_chunks = get_notebook_chunks(user_id, notebook_id, allowed)
        results = [
            {
                "source": chunk.get("source", "unknown source"),
                "text": chunk.get("text", ""),
                "score": 0.0,
                "retrieval_method": "notebook_overview",
            }
            for chunk in raw_chunks[:max(top_k, 12)]
        ]

    blocks = []
    for index, result in enumerate(results, 1):
        blocks.append(
            f"[Source {index}: {result.get('source', 'unknown source')}]\n"
            f"{result.get('text', '').strip()}"
        )

    insights = _insights(notebook_id, allowed) if include_insights else []
    for insight in insights[:8]:
        blocks.append(
            f"[Persisted insight: {insight.get('source_name', 'source')} / {insight.get('insight_type', 'insight')}]\n"
            f"{insight.get('content', '').strip()}"
        )

    text = _fit_blocks(blocks, token_budget) if blocks else ""
    sources = list(dict.fromkeys(str(result.get("source", "unknown source")) for result in results if result.get("source")))
    return ContextResult(text=text, sources=sources, chunks=results, insights=insights)
