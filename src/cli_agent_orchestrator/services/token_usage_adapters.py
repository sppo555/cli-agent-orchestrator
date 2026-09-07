"""Strict native usage adapters for evidence-approved providers.

The adapters only inspect complete JSON objects or JSONL events. They never
search ordinary terminal prose for numbers, so a normal response cannot become
false native usage.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Mapping, Optional

from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.services.token_usage_contract import NativeUsage

logger = logging.getLogger(__name__)


def _json_objects(raw: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(raw, Mapping):
        yield raw
        return
    if not isinstance(raw, str):
        return
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, Mapping):
        yield parsed
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed_line = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed_line, Mapping):
            yield parsed_line


def _native_usage(value: Any) -> Optional[NativeUsage]:
    if not isinstance(value, Mapping):
        return None
    required = ("input_tokens", "output_tokens")
    if any(key not in value for key in required):
        return None
    counts = {key: value[key] for key in required}
    if any(
        isinstance(number, bool) or not isinstance(number, int) or number < 0
        for number in counts.values()
    ):
        return None
    total = value.get("total_tokens", counts["input_tokens"] + counts["output_tokens"])
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        return None
    if total != counts["input_tokens"] + counts["output_tokens"]:
        return None
    model = value.get("model")
    return NativeUsage(
        input_tokens=counts["input_tokens"],
        output_tokens=counts["output_tokens"],
        total_tokens=total,
        model=model if isinstance(model, str) and model else None,
    )


def extract_claude_code_usage(raw_output: Any) -> Optional[NativeUsage]:
    """Extract the last valid Claude result/assistant usage object.

    Claude reports uncached, cache-creation, and cache-read input separately.
    All three are provider-processed input tokens; omitting the cache fields can
    turn a real 190k-token turn into a misleading ``input_tokens=2`` record.
    """

    found: Optional[NativeUsage] = None
    for event in _json_objects(raw_output):
        event_type = event.get("type")
        candidates: list[Any] = []
        if event_type == "result":
            candidates.append(event.get("usage"))
        if event_type == "assistant" and isinstance(event.get("message"), Mapping):
            message = event["message"]
            candidates.append(message.get("usage"))
            if isinstance(message.get("model"), str):
                candidates.append({**(message.get("usage") or {}), "model": message["model"]})
        for candidate in candidates:
            normalized = candidate
            if isinstance(candidate, Mapping):
                uncached = candidate.get("input_tokens")
                cache_creation = candidate.get("cache_creation_input_tokens", 0)
                cache_read = candidate.get("cache_read_input_tokens", 0)
                if all(
                    isinstance(value, int) and not isinstance(value, bool) and value >= 0
                    for value in (uncached, cache_creation, cache_read)
                ):
                    normalized = {
                        **candidate,
                        "input_tokens": uncached + cache_creation + cache_read,
                    }
                    # Claude's result object may omit total_tokens or define it
                    # without cache input. Recompute against the normalized
                    # input/output contract used by the dashboard.
                    output = candidate.get("output_tokens")
                    if isinstance(output, int) and not isinstance(output, bool) and output >= 0:
                        normalized["total_tokens"] = normalized["input_tokens"] + output
            usage = _native_usage(normalized)
            if usage is not None:
                found = usage
    return found


def _claude_message_text(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for block in value:
        if not isinstance(block, Mapping):
            continue
        if block.get("type") in {"text", "output_text"} and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts) or None


def extract_claude_code_last_message(raw_output: Any) -> str:
    """Extract the final response from Claude's structured JSON output."""

    final_result: Optional[str] = None
    assistant_message: Optional[str] = None
    for event in _json_objects(raw_output):
        if event.get("type") == "result":
            result = _claude_message_text(event.get("result"))
            if result is not None:
                final_result = result
        if event.get("type") == "assistant" and isinstance(event.get("message"), Mapping):
            message = event["message"]
            text = _claude_message_text(message.get("content"))
            if text is not None:
                assistant_message = text
    return final_result if final_result is not None else (assistant_message or "")


def extract_codex_usage(raw_output: Any) -> Optional[NativeUsage]:
    """Extract usage from Codex structured turn-completed JSONL events."""

    found: Optional[NativeUsage] = None
    for event in _json_objects(raw_output):
        candidates: list[Any] = []
        if event.get("type") == "turn.completed":
            candidates.append(event.get("usage"))
        if event.get("method") == "turn/completed":
            params = event.get("params")
            if isinstance(params, Mapping) and isinstance(params.get("turn"), Mapping):
                candidates.append(params["turn"].get("usage"))
        for candidate in candidates:
            usage = _native_usage(candidate)
            if usage is not None:
                found = usage
    return found


def _message_text(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for block in value:
        if not isinstance(block, Mapping):
            continue
        text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts) or None


def extract_codex_last_message(raw_output: Any) -> str:
    """Extract the final assistant message from Codex structured JSONL only.

    This parser intentionally accepts event envelopes emitted by the structured
    Codex command and does not inspect terminal prose or rollout/session files.
    Completed item events win over streaming deltas when both are present.
    """

    last_completed: Optional[str] = None
    deltas: list[str] = []
    for event in _json_objects(raw_output):
        event_type = event.get("type") or event.get("method")
        item = event.get("item")
        if isinstance(item, Mapping):
            item_type = item.get("type")
            if item_type in {"agent_message", "agentMessage", "assistant_message"}:
                text = _message_text(item.get("text"))
                if text is None:
                    text = _message_text(item.get("content"))
                if text is not None and event_type in {"item.completed", "item/completed"}:
                    last_completed = text
        if event_type in {"item/agent_message/delta", "item.agent_message.delta"}:
            delta = event.get("delta")
            if isinstance(delta, str):
                deltas.append(delta)
        if event_type in {"agent_message", "agentMessage"}:
            text = _message_text(event.get("text"))
            if text is not None:
                last_completed = text
    return last_completed if last_completed is not None else "".join(deltas)


def extract_grok_cli_usage(raw_output: Any) -> Optional[NativeUsage]:
    """Extract Grok's final, process-local streaming JSON usage event.

    Grok reports cache-read input separately while ``total_tokens`` includes it.
    Reasoning tokens are already included in ``output_tokens`` and therefore are
    not added a second time.  Only a terminal ``end`` event is accepted.
    """

    found: Optional[NativeUsage] = None
    for event in _json_objects(raw_output):
        if event.get("type") != "end":
            continue
        candidate = event.get("usage")
        if not isinstance(candidate, Mapping):
            continue
        uncached = candidate.get("input_tokens")
        cache_read = candidate.get("cache_read_input_tokens", 0)
        output = candidate.get("output_tokens")
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (uncached, cache_read, output)
        ):
            continue
        normalized = {
            "input_tokens": uncached + cache_read,
            "output_tokens": output,
            "total_tokens": candidate.get("total_tokens"),
        }
        model_usage = event.get("modelUsage")
        if isinstance(model_usage, Mapping) and len(model_usage) == 1:
            model = next(iter(model_usage))
            if isinstance(model, str) and model:
                normalized["model"] = model
        usage = _native_usage(normalized)
        if usage is not None:
            found = usage
    return found


def extract_grok_cli_last_message(raw_output: Any) -> str:
    """Join only Grok streaming JSON ``text`` events into the final response."""

    parts: list[str] = []
    for event in _json_objects(raw_output):
        if event.get("type") == "text" and isinstance(event.get("data"), str):
            parts.append(event["data"])
    return "".join(parts)


def extract_native_usage(provider: str, raw_output: Any) -> Optional[NativeUsage]:
    if provider == ProviderType.CLAUDE_CODE.value:
        return extract_claude_code_usage(raw_output)
    if provider == ProviderType.CODEX.value:
        return extract_codex_usage(raw_output)
    if provider == ProviderType.GROK_CLI.value:
        return extract_grok_cli_usage(raw_output)
    return None
