"""Native token accounting for interactive Claude Code, Codex, and Agy turns.

The normal CAO ``assign`` path keeps workers in interactive tmux terminals.  It
therefore cannot consume the structured stdout used by ``structured_worker``.
This module bridges that gap without scraping terminal text: it reads only the
provider-owned usage fields in Claude session JSONL, Codex rollout JSONL, and
Agy conversation metadata. Prompt, response, tool payload, and transcript
content are never persisted.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.models.token_usage import TokenUsage
from cli_agent_orchestrator.services.token_usage import (
    persist_worker_token_usage,
    resolve_worker_configuration,
    resolve_worker_progress,
)

logger = logging.getLogger(__name__)

_NATIVE_INTERACTIVE_PROVIDERS = {
    ProviderType.CLAUDE_CODE.value,
    ProviderType.CODEX.value,
    ProviderType.ANTIGRAVITY_CLI.value,
}
_CAPTURE_RETRY_DELAYS = (0.0, 0.2, 0.5)


@dataclass(frozen=True)
class _TokenTotals:
    input_tokens: int
    output_tokens: int
    model: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class InteractiveUsageTurn:
    """A claimed interactive turn, safe to finish off the event loop."""

    terminal_id: str
    provider: str
    agent: str
    session_name: str
    window_name: str
    progress: Optional[str]
    source_path: Optional[Path]
    marker: Any


_lock = threading.RLock()
_active_turns: dict[str, InteractiveUsageTurn] = {}
_codex_sources: dict[str, Path] = {}
_agy_sources: dict[str, Path] = {}
_processing_observed: set[str] = set()
_capture_in_flight: set[str] = set()


def claude_usage_session_id(terminal_id: str, session_name: str, window_name: str) -> str:
    """Return the stable UUID passed to Claude's ``--session-id`` option.

    Stability lets a restarted cao-server reconstruct the same provider hint
    from terminal metadata without adding transcript paths to the CAO database.
    """

    key = f"cao-interactive:{session_name}:{window_name}:{terminal_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _claude_source_path(turn: InteractiveUsageTurn) -> Optional[Path]:
    session_id = claude_usage_session_id(
        turn.terminal_id,
        turn.session_name,
        turn.window_name,
    )
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return None
    try:
        return next(projects.rglob(f"{session_id}.jsonl"))
    except (StopIteration, OSError):
        return None


def _descendant_pids(root_pid: int) -> list[int]:
    """Return ``root_pid`` plus descendants using the portable ``ps`` table."""

    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid="],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [root_pid]

    children: dict[int, list[int]] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            pid, parent = (int(fields[0]), int(fields[1]))
        except ValueError:
            continue
        children.setdefault(parent, []).append(pid)

    found: list[int] = []
    pending = [root_pid]
    while pending:
        pid = pending.pop()
        if pid in found:
            continue
        found.append(pid)
        pending.extend(children.get(pid, ()))
    return found


def _discover_codex_rollout(session_name: str, window_name: str) -> Optional[Path]:
    """Find the rollout opened by the Codex process in one tmux pane.

    Process ownership is the correlation boundary.  We intentionally do not
    choose the newest rollout by cwd: concurrent workers commonly share a cwd,
    and a timestamp heuristic could attribute another worker's usage.
    """

    target = f"{session_name}:{window_name}"
    try:
        pane = subprocess.run(
            ["tmux", "display-message", "-p", "-t", target, "#{pane_pid}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        pane_pid = int(pane.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None

    pids = _descendant_pids(pane_pid)
    try:
        opened = subprocess.run(
            ["lsof", "-Fn", "-p", ",".join(str(pid) for pid in pids)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    candidates: list[Path] = []
    for line in opened.stdout.splitlines():
        if not line.startswith("n"):
            continue
        path = Path(line[1:])
        if path.name.startswith("rollout-") and path.suffix == ".jsonl" and path.exists():
            candidates.append(path)
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda path: path.stat().st_mtime_ns)
    except OSError:
        return None


def _pane_working_directory(session_name: str, window_name: str) -> Optional[str]:
    target = f"{session_name}:{window_name}"
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", target, "#{pane_current_path}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    working_directory = result.stdout.strip()
    return working_directory or None


def _discover_agy_conversation(session_name: str, window_name: str) -> Optional[Path]:
    """Resolve the conversation DB from Agy's cwd-to-conversation cache.

    CAO launches every Agy worker in a terminal-specific workspace directory.
    Agy owns the cache mapping that directory to its active conversation id,
    which is a stronger correlation boundary than timestamps or shared source
    repository paths.
    """

    working_directory = _pane_working_directory(session_name, window_name)
    if working_directory is None:
        return None
    cache = Path.home() / ".gemini" / "antigravity-cli" / "cache" / "last_conversations.json"
    try:
        mapping = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(mapping, dict):
        return None
    conversation_id = mapping.get(working_directory)
    if (
        not isinstance(conversation_id, str)
        or not conversation_id
        or Path(conversation_id).name != conversation_id
    ):
        return None
    source = Path.home() / ".gemini" / "antigravity-cli" / "conversations" / f"{conversation_id}.db"
    return source if source.is_file() else None


def _protobuf_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("truncated protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
    raise ValueError("protobuf varint exceeds 64 bits")


def _protobuf_fields(data: bytes) -> dict[int, list[int | bytes]]:
    """Decode only protobuf wire primitives needed by Agy metadata."""

    fields: dict[int, list[int | bytes]] = {}
    offset = 0
    while offset < len(data):
        tag, offset = _protobuf_varint(data, offset)
        field_number, wire_type = tag >> 3, tag & 7
        if field_number <= 0:
            raise ValueError("invalid protobuf field")
        if wire_type == 0:
            value, offset = _protobuf_varint(data, offset)
        elif wire_type == 1:
            if offset + 8 > len(data):
                raise ValueError("truncated protobuf fixed64")
            value = data[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            size, offset = _protobuf_varint(data, offset)
            if size < 0 or offset + size > len(data):
                raise ValueError("truncated protobuf bytes")
            value = data[offset : offset + size]
            offset += size
        elif wire_type == 5:
            if offset + 4 > len(data):
                raise ValueError("truncated protobuf fixed32")
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise ValueError("unsupported protobuf wire type")
        fields.setdefault(field_number, []).append(value)
    return fields


def _agy_generation_totals(data: bytes) -> Optional[_TokenTotals]:
    """Read Agy GenerationMetadata.input_tokens/output_tokens only.

    Agy 1.1.x stores a trajectory wrapper at field 1 and its generation
    metadata at wrapper field 4. GenerationMetadata fields 2 and 3 are the
    provider-reported input and output counters. Other fields and all payload
    content are deliberately ignored.
    """

    try:
        root = _protobuf_fields(data)
        totals: list[_TokenTotals] = []
        for wrapper_raw in root.get(1, ()):
            if not isinstance(wrapper_raw, bytes):
                continue
            wrapper = _protobuf_fields(wrapper_raw)
            for generation_raw in wrapper.get(4, ()):
                if not isinstance(generation_raw, bytes):
                    continue
                generation = _protobuf_fields(generation_raw)
                latency = next(
                    (value for value in generation.get(1, ()) if isinstance(value, int)),
                    None,
                )
                input_tokens = next(
                    (value for value in generation.get(2, ()) if isinstance(value, int)),
                    None,
                )
                output_tokens = next(
                    (value for value in generation.get(3, ()) if isinstance(value, int)),
                    None,
                )
                model_enum = next(
                    (value for value in generation.get(6, ()) if isinstance(value, int)),
                    None,
                )
                if (
                    latency is None
                    or input_tokens is None
                    or output_tokens is None
                    or model_enum is None
                    or input_tokens <= 0
                ):
                    continue
                totals.append(_TokenTotals(input_tokens, output_tokens))
    except (TypeError, ValueError):
        return None
    if not totals:
        return None
    return _TokenTotals(
        input_tokens=sum(item.input_tokens for item in totals),
        output_tokens=sum(item.output_tokens for item in totals),
    )


def _agy_last_generation_index(path: Path) -> Optional[int]:
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)) as connection:
            row = connection.execute("SELECT MAX(idx) FROM gen_metadata").fetchone()
    except (OSError, sqlite3.Error):
        return None
    return row[0] if row and isinstance(row[0], int) else -1


def _agy_totals_after(path: Path, marker: int) -> Optional[_TokenTotals]:
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)) as connection:
            rows = connection.execute(
                "SELECT data FROM gen_metadata WHERE idx > ? ORDER BY idx",
                (marker,),
            ).fetchall()
    except (OSError, sqlite3.Error):
        return None
    totals = [
        parsed
        for (data,) in rows
        if isinstance(data, bytes) and (parsed := _agy_generation_totals(data)) is not None
    ]
    if not totals:
        return None
    return _TokenTotals(
        input_tokens=sum(item.input_tokens for item in totals),
        output_tokens=sum(item.output_tokens for item in totals),
    )


def _read_jsonl_from(path: Path, offset: int = 0) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            raw = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _non_negative_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _claude_totals(path: Path, offset: int) -> Optional[_TokenTotals]:
    """Sum unique Claude API messages after ``offset`` including cache input."""

    messages: dict[str, tuple[int, int, Optional[str]]] = {}
    for index, event in enumerate(_read_jsonl_from(path, offset)):
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        input_tokens = _non_negative_int(usage.get("input_tokens"))
        output_tokens = _non_negative_int(usage.get("output_tokens"))
        cache_creation = _non_negative_int(usage.get("cache_creation_input_tokens", 0))
        cache_read = _non_negative_int(usage.get("cache_read_input_tokens", 0))
        if None in (input_tokens, output_tokens, cache_creation, cache_read):
            continue
        message_id = message.get("id")
        dedupe_key = message_id if isinstance(message_id, str) and message_id else f"event-{index}"
        model = message.get("model")
        messages[dedupe_key] = (
            input_tokens + cache_creation + cache_read,
            output_tokens,
            model if isinstance(model, str) and model else None,
        )
    if not messages:
        return None
    return _TokenTotals(
        input_tokens=sum(value[0] for value in messages.values()),
        output_tokens=sum(value[1] for value in messages.values()),
        model=next((value[2] for value in reversed(tuple(messages.values())) if value[2]), None),
    )


def _codex_cumulative_totals(path: Path) -> Optional[_TokenTotals]:
    found: Optional[_TokenTotals] = None
    for event in _read_jsonl_from(path):
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        usage = info.get("total_token_usage") if isinstance(info, dict) else None
        if not isinstance(usage, dict):
            continue
        input_tokens = _non_negative_int(usage.get("input_tokens"))
        output_tokens = _non_negative_int(usage.get("output_tokens"))
        total_tokens = _non_negative_int(usage.get("total_tokens"))
        if None in (input_tokens, output_tokens, total_tokens):
            continue
        if total_tokens != input_tokens + output_tokens:
            continue
        found = _TokenTotals(input_tokens=input_tokens, output_tokens=output_tokens)
    return found


def begin_interactive_usage_turn(
    *,
    terminal_id: str,
    provider: str,
    agent: str,
    session_name: str,
    window_name: str,
    prompt: str,
) -> bool:
    """Snapshot native usage immediately before one interactive prompt.

    Returns true only when this call created the active marker.  A second input
    queued while the worker is still processing is folded into the same native
    turn instead of resetting the baseline and losing usage.
    """

    if provider not in _NATIVE_INTERACTIVE_PROVIDERS:
        return False
    with _lock:
        if terminal_id in _active_turns:
            return False

        progress = resolve_worker_progress(None, prompt, "")
        source_path: Optional[Path]
        marker: Any
        if provider == ProviderType.CLAUDE_CODE.value:
            provisional = InteractiveUsageTurn(
                terminal_id=terminal_id,
                provider=provider,
                agent=agent,
                session_name=session_name,
                window_name=window_name,
                progress=progress,
                source_path=None,
                marker=0,
            )
            source_path = _claude_source_path(provisional)
            try:
                marker = source_path.stat().st_size if source_path is not None else 0
            except OSError:
                marker = 0
        elif provider == ProviderType.CODEX.value:
            source_path = _codex_sources.get(terminal_id)
            if source_path is None or not source_path.exists():
                source_path = _discover_codex_rollout(session_name, window_name)
                if source_path is not None:
                    _codex_sources[terminal_id] = source_path
            marker = _codex_cumulative_totals(source_path) if source_path is not None else None
        else:
            source_path = _agy_sources.get(terminal_id)
            if source_path is None or not source_path.exists():
                source_path = _discover_agy_conversation(session_name, window_name)
                if source_path is not None:
                    _agy_sources[terminal_id] = source_path
            if source_path is None:
                return False
            marker = _agy_last_generation_index(source_path)
            if marker is None:
                return False

        _active_turns[terminal_id] = InteractiveUsageTurn(
            terminal_id=terminal_id,
            provider=provider,
            agent=agent,
            session_name=session_name,
            window_name=window_name,
            progress=progress,
            source_path=source_path,
            marker=marker,
        )
        _processing_observed.discard(terminal_id)
        _capture_in_flight.discard(terminal_id)
        return True


def observe_interactive_usage_processing(terminal_id: str) -> bool:
    """Arm completion only after this active turn reaches PROCESSING."""

    with _lock:
        if terminal_id not in _active_turns:
            return False
        _processing_observed.add(terminal_id)
        return True


def cancel_interactive_usage_turn(terminal_id: str) -> None:
    """Discard a marker when prompt delivery failed before submission."""

    with _lock:
        _active_turns.pop(terminal_id, None)
        _processing_observed.discard(terminal_id)
        _capture_in_flight.discard(terminal_id)


def claim_completed_interactive_usage_turn(terminal_id: str) -> Optional[InteractiveUsageTurn]:
    """Reserve an eligible completed marker for asynchronous persistence.

    The marker stays active until provider usage is actually found and
    persisted.  A stale ready edge can therefore produce a zero delta without
    consuming the real turn that completes later.
    """

    with _lock:
        if terminal_id not in _processing_observed or terminal_id in _capture_in_flight:
            return None
        turn = _active_turns.get(terminal_id)
        if turn is None:
            return None
        _capture_in_flight.add(terminal_id)
        return turn


def _finish_interactive_usage_claim(turn: InteractiveUsageTurn, *, consumed: bool) -> None:
    with _lock:
        _capture_in_flight.discard(turn.terminal_id)
        if consumed and _active_turns.get(turn.terminal_id) is turn:
            _active_turns.pop(turn.terminal_id, None)
            _processing_observed.discard(turn.terminal_id)


def finalize_interactive_usage_terminal(terminal_id: str) -> Optional[TokenUsage]:
    """Flush an active native turn before its terminal/provider is destroyed."""

    with _lock:
        turn = _active_turns.get(terminal_id)
        if turn is None or terminal_id in _capture_in_flight:
            return None
        _capture_in_flight.add(terminal_id)
    return complete_interactive_usage_turn(turn)


def clear_interactive_usage_terminal(terminal_id: str) -> None:
    with _lock:
        _active_turns.pop(terminal_id, None)
        _codex_sources.pop(terminal_id, None)
        _agy_sources.pop(terminal_id, None)
        _processing_observed.discard(terminal_id)
        _capture_in_flight.discard(terminal_id)


def _usage_for_turn(turn: InteractiveUsageTurn) -> Optional[TokenUsage]:
    source_path = turn.source_path
    if turn.provider == ProviderType.CLAUDE_CODE.value:
        source_path = source_path or _claude_source_path(turn)
        if source_path is None:
            return None
        totals = _claude_totals(source_path, int(turn.marker or 0))
    elif turn.provider == ProviderType.CODEX.value:
        if source_path is None or not source_path.exists():
            source_path = _discover_codex_rollout(turn.session_name, turn.window_name)
        if source_path is None:
            return None
        current = _codex_cumulative_totals(source_path)
        if current is None:
            return None
        baseline = turn.marker if isinstance(turn.marker, _TokenTotals) else _TokenTotals(0, 0)
        input_tokens = current.input_tokens - baseline.input_tokens
        output_tokens = current.output_tokens - baseline.output_tokens
        if input_tokens < 0 or output_tokens < 0:
            return None
        totals = _TokenTotals(input_tokens=input_tokens, output_tokens=output_tokens)
    else:
        if source_path is None or not source_path.exists():
            return None
        marker = turn.marker if isinstance(turn.marker, int) else -1
        totals = _agy_totals_after(source_path, marker)

    if totals is None or totals.total_tokens <= 0:
        return None
    configured_model, effort = resolve_worker_configuration(turn.provider, turn.agent)
    return TokenUsage(
        input_tokens=totals.input_tokens,
        output_tokens=totals.output_tokens,
        total_tokens=totals.total_tokens,
        estimated=False,
        model=totals.model or configured_model,
        effort=effort,
        progress=turn.progress,
    )


def complete_interactive_usage_turn(turn: InteractiveUsageTurn) -> Optional[TokenUsage]:
    """Read and persist one claimed native turn; never fail terminal status."""

    try:
        usage: Optional[TokenUsage] = None
        for delay in _CAPTURE_RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            usage = _usage_for_turn(turn)
            if usage is not None:
                break
        if usage is None:
            _finish_interactive_usage_claim(turn, consumed=False)
            logger.warning(
                "No native interactive usage found for %s terminal %s; marker retained",
                turn.provider,
                turn.terminal_id,
            )
            return None
        persist_worker_token_usage(
            terminal_id=turn.terminal_id,
            provider=turn.provider,
            agent=turn.agent,
            usage=usage,
            progress=turn.progress,
        )
        _finish_interactive_usage_claim(turn, consumed=True)
        return usage
    except Exception:  # noqa: BLE001 - observability must never break worker completion
        _finish_interactive_usage_claim(turn, consumed=False)
        logger.exception("Failed to capture native interactive usage for %s", turn.terminal_id)
        return None
