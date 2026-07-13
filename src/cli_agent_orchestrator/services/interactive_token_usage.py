"""Native token accounting for interactive Claude Code and Codex turns.

The normal CAO ``assign`` path keeps workers in interactive tmux terminals.  It
therefore cannot consume the structured stdout used by ``structured_worker``.
This module bridges that gap without scraping terminal text: it reads only the
provider-owned usage fields in Claude session JSONL and Codex rollout JSONL.
Prompt, response, tool payload, and transcript content are never persisted.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
import uuid
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
        else:
            source_path = _codex_sources.get(terminal_id)
            if source_path is None or not source_path.exists():
                source_path = _discover_codex_rollout(session_name, window_name)
                if source_path is not None:
                    _codex_sources[terminal_id] = source_path
            marker = _codex_cumulative_totals(source_path) if source_path is not None else None

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
        return True


def cancel_interactive_usage_turn(terminal_id: str) -> None:
    """Discard a marker when prompt delivery failed before submission."""

    with _lock:
        _active_turns.pop(terminal_id, None)


def claim_completed_interactive_usage_turn(terminal_id: str) -> Optional[InteractiveUsageTurn]:
    """Atomically detach a completed marker before asynchronous persistence."""

    with _lock:
        return _active_turns.pop(terminal_id, None)


def clear_interactive_usage_terminal(terminal_id: str) -> None:
    with _lock:
        _active_turns.pop(terminal_id, None)
        _codex_sources.pop(terminal_id, None)


def _usage_for_turn(turn: InteractiveUsageTurn) -> Optional[TokenUsage]:
    source_path = turn.source_path
    if turn.provider == ProviderType.CLAUDE_CODE.value:
        source_path = source_path or _claude_source_path(turn)
        if source_path is None:
            return None
        totals = _claude_totals(source_path, int(turn.marker or 0))
    else:
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
            logger.warning(
                "No native interactive usage found for %s terminal %s; record omitted",
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
        return usage
    except Exception:  # noqa: BLE001 - observability must never break worker completion
        logger.exception("Failed to capture native interactive usage for %s", turn.terminal_id)
        return None
