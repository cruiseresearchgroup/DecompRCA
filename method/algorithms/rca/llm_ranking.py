"""Prompts and tracing helpers for the LLM reranker.

The reranker itself (candidate retrieval, evidence rendering, the LLM call,
parsing, and caching) lives in `method/runners/_common.py`; this module holds
the two prompt builders it uses and an optional Langfuse run summary.
"""

from __future__ import annotations

import os

# Optional Langfuse tracing (no-op if not configured)
try:
    from langfuse import get_client
    _LANGFUSE = get_client() if os.environ.get("LANGFUSE_PUBLIC_KEY") else None
except Exception:
    _LANGFUSE = None


def build_system_prompt(level: str, domain_phrase: str, domain_context: str) -> str:
    """Build the LLM system prompt for one RCA call.

    Two branches, matching the paper's two DK conditions:

      ``level == "none"``  → domain-neutral framing. Used for the no-DK rows
          in Tables 5 / 6. The LLM is told it is an expert in RCA over
          time-series anomalies but is **not** told which domain the data
          comes from (HVAC, water-treatment, microservice, etc.).

      otherwise            → dataset-specific framing. The LLM is told the
          domain via ``{domain_phrase}`` (a complete noun phrase like
          ``"HVAC rooftop-unit systems"`` or
          ``"an Online Boutique e-commerce microservice platform"``) and is
          handed the ``{domain_context}`` document (the Light variant used
          in the paper) as operational documentation.
    """
    if level == "none" or not domain_context.strip():
        return (
            "You are an expert in root cause analysis of complex systems "
            "based on time-series anomaly evidence."
        )
    return (
        f"You are an expert in {domain_phrase} and root cause analysis. "
        "Use the following operational system documentation to inform "
        f"your reasoning:\n\n{domain_context}"
    )


def build_hybrid_clean_user_prompt(anomaly_summary: str) -> str:
    """Canonical hybrid_clean user prompt — shared across all datasets.

    Wraps the per-scenario ``anomaly_summary`` (already rendered with
    magnitude / onset / state-change evidence) in a dataset-agnostic
    framing that asks the LLM for a reasoning trace and a ranked list.
    """
    return (
        "A fault has been detected. The following items are candidates for "
        "root cause analysis, ranked by deviation from baseline behaviour. "
        "Each line shows the item name, its deviation magnitude, when it "
        "first deviated, and its before/after values.\n\n"
        f"{anomaly_summary}\n\n"
        "Respond with a single JSON object containing BOTH a reasoning trace\n"
        "and the ranked list:\n\n"
        "{\n"
        "  \"reasoning\": \"<your detailed step-by-step analysis identifying "
        "the root cause and explaining why each top-ranked item was chosen "
        "over others>\",\n"
        "  \"ranked\": [\"item1\", \"item2\", ...]\n"
        "}\n\n"
        "Only include items from the provided list. Output only the JSON."
    )


def log_run_summary(
    session_id: str | None,
    run_name: str | None,
    name_suffix: str,
    metrics: dict,
    metadata: dict | None = None,
    tags: list[str] | None = None,
) -> None:
    """Emit a Langfuse 'summary' trace under the same session as the per-
    scenario traces. The trace's output is the aggregate metrics dict so it
    appears in the Langfuse UI as the last row of the session.

    Safe to call when Langfuse is not configured — becomes a no-op.
    """
    if _LANGFUSE is None:
        return
    try:
        trace_name = f"summary::{name_suffix}"
        with _LANGFUSE.start_as_current_span(
            name=trace_name,
            input={"summary_for": name_suffix, **(metadata or {})},
        ) as span:
            span.update(output=metrics)
            update_kwargs = dict(
                name=trace_name,
                input={"summary_for": name_suffix},
                output=metrics,
                metadata={**(metadata or {}), "metrics": metrics, "run_name": run_name},
                tags=["summary", *(tags or [])],
            )
            if session_id:
                update_kwargs["session_id"] = session_id
            _LANGFUSE.update_current_trace(**update_kwargs)
    except Exception as e:
        print(f"    [Langfuse] summary log failed: {e}")
