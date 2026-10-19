import hashlib
import hmac
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


def tracing_enabled() -> bool:
    return (
        os.getenv("MULEWATCH_TRACING_ENABLED") == "1"
        and bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
        and bool(os.getenv("LANGFUSE_SECRET_KEY"))
    )


def prompt_version_id(prompt_path: Path) -> str:
    digest = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    return f"{prompt_path.stem}@{digest[:12]}"


def investigation_trace_seed(thread_id: str, secret: str) -> str:
    """Derive a stable, pseudonymous trace seed."""
    if not thread_id or not secret:
        raise ValueError("Trace correlation requires a thread ID and secret")
    return hmac.new(
        secret.encode("utf-8"),
        thread_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def configured_trace_seed(thread_id: str) -> str | None:
    """Return a correlation seed only when tracing is configured."""
    if not tracing_enabled():
        return None
    secret = os.getenv("MULEWATCH_TRACING_CORRELATION_SECRET")
    if not secret:
        return None
    return investigation_trace_seed(thread_id, secret)


def safe_investigation_metrics(state: dict) -> dict:
    metrics = {}
    for key in ("input_tokens", "output_tokens", "steps_taken"):
        value = state.get(key)
        if type(value) is int and value >= 0:
            metrics[key] = value
    cost = state.get("estimated_cost_usd")
    if type(cost) in (int, float) and 0 <= cost < float("inf"):
        metrics["estimated_cost_usd"] = float(cost)
    limit_hit = state.get("limit_hit")
    if type(limit_hit) is bool:
        metrics["limit_hit"] = limit_hit
    status = state.get("status")
    allowed = {
        "COMPLETE",
        "AWAITING_REVIEW",
        "INSUFFICIENT_EVIDENCE",
        "NEEDS_MANUAL_REVIEW",
    }
    if type(status) is str and status in allowed:
        metrics["outcome"] = status
        metrics["fallback"] = status in {
            "INSUFFICIENT_EVIDENCE",
            "NEEDS_MANUAL_REVIEW",
        }
    return metrics


class SafeTracingHandler(BaseCallbackHandler):
    """Export operational metadata only, never investigation content."""

    raise_error = False

    def __init__(self, client, root):
        self.client = client
        self.root = root
        self.runs = {}
        self.started = {}

    def record_metrics(self, state: dict) -> None:
        try:
            metrics = safe_investigation_metrics(state)
            if metrics:
                self.root.update(metadata=metrics)
        except Exception:
            logger.warning("Tracing metrics update failed", exc_info=False)

    def _start(
        self,
        run_id: UUID,
        name: str,
        kind: str,
        parent_run_id: UUID | None = None,
    ):
        try:
            parent = self.runs.get(parent_run_id, self.root)
            observation = parent.start_observation(name=name, as_type=kind)
            self.runs[run_id] = observation
            self.started[run_id] = time.perf_counter()
        except Exception:
            logger.warning("Tracing start failed", exc_info=False)

    def _end(self, run_id: UUID, **metadata):
        observation = self.runs.pop(run_id, None)
        started = self.started.pop(run_id, None)
        if observation is None:
            return
        try:
            if started is not None:
                metadata["duration_ms"] = round(
                    (time.perf_counter() - started) * 1000, 2
                )
            observation.update(metadata=metadata)
            observation.end()
        except Exception:
            logger.warning("Tracing end failed", exc_info=False)

    def on_chain_start(
        self,
        serialized,
        inputs,
        *,
        run_id,
        parent_run_id=None,
        tags=None,
        metadata=None,
        **kwargs,
    ):
        name = kwargs.get("name") or "chain"
        allowed = {
            "load_alert",
            "investigate",
            "tools",
            "ensure_typology",
            "assess",
            "verify",
            "save",
            "review",
        }
        safe_name = name if name in allowed else "graph_operation"
        self._start(run_id, safe_name, "span", parent_run_id)

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        self._end(run_id, status="completed")

    def on_chain_error(self, error, *, run_id, **kwargs):
        self._end(run_id, status="error")

    def on_chat_model_start(
        self, serialized, messages, *, run_id, parent_run_id=None, **kwargs
    ):
        self._start(run_id, "llm_call", "generation", parent_run_id)

    def on_llm_end(self, response, *, run_id, **kwargs):
        input_tokens = 0
        output_tokens = 0
        try:
            for group in response.generations:
                for generation in group:
                    usage = getattr(generation.message, "usage_metadata", None) or {}
                    input_tokens += usage.get("input_tokens", 0)
                    output_tokens += usage.get("output_tokens", 0)
        except AttributeError, TypeError, ValueError:
            pass
        observation = self.runs.get(run_id)
        if observation is not None:
            try:
                observation.update(
                    usage_details={"input": input_tokens, "output": output_tokens}
                )
            except Exception:
                logger.warning("Tracing usage update failed", exc_info=False)
        self._end(run_id, status="completed")

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._end(run_id, status="error")

    def on_tool_start(
        self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs
    ):
        allowed = {
            "account_activity_tool",
            "account_score_tool",
            "typology_search_tool",
        }
        name = (serialized or {}).get("name", "")
        self._start(
            run_id,
            name if name in allowed else "tool_call",
            "tool",
            parent_run_id,
        )

    def on_tool_end(self, output, *, run_id, **kwargs):
        self._end(run_id, status="completed")

    def on_tool_error(self, error, *, run_id, **kwargs):
        self._end(run_id, status="error")


@contextmanager
def investigation_trace(
    *,
    source: str,
    model: str,
    prompt_version: str,
    git_sha: str,
    correlation_seed: str | None = None,
):
    if not tracing_enabled():
        yield None
        return
    try:
        from langfuse import get_client

        client = get_client()
        trace_context = None
        if correlation_seed is not None:
            trace_context = {
                "trace_id": client.create_trace_id(seed=correlation_seed),
            }
        root = client.start_observation(
            trace_context=trace_context,
            name="mulewatch_investigation",
            as_type="agent",
            metadata={
                "source": source,
                "model": model,
                "prompt_version": prompt_version,
                "git_sha": git_sha,
            },
        )
    except Exception:
        logger.warning("Tracing initialization failed", exc_info=False)
        yield None
        return

    handler = SafeTracingHandler(client, root)
    started = time.perf_counter()
    try:
        yield handler
    except BaseException:
        try:
            root.update(
                metadata={
                    "status": "error",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
        except Exception:
            logger.warning("Tracing error update failed", exc_info=False)
        raise
    else:
        try:
            root.update(
                metadata={
                    "status": "completed",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
        except Exception:
            logger.warning("Tracing completion update failed", exc_info=False)
    finally:
        try:
            for run_id in list(handler.runs):
                handler._end(run_id, status="unfinished")
            root.end()
        except Exception:
            logger.warning("Tracing cleanup failed", exc_info=False)
