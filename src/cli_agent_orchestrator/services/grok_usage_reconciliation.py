"""Out-of-band upgrade of estimated Grok rows to provider-native counts.

Interactive Grok turns only flush their ``turn_completed`` usage record when the
whole turn finally ends. A turn that closes with long-running backgrounded shell
tasks (e.g. an e2e suite) can flush that record minutes after CAO has already
captured usage, fallen back to a character estimate, and torn the terminal down.

This module records a bounded, metadata-only reconciliation hint for each such
estimated Grok row and later re-reads the exact ``updates.jsonl`` the worker
used. When a valid ``turn_completed`` delta over the stored baseline appears,
the estimated row is upgraded in place to native counts. Hints never contain
prompt, response, or transcript content — only the session file path, the
session id filter, and the baseline token counts.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

RECONCILE_VERSION = 1
_DEFAULT_TTL_SECONDS = 2 * 60 * 60
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024


class GrokReconcileHint(BaseModel):
    """Versioned, privacy-bounded hint for one estimated Grok attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = RECONCILE_VERSION
    record_id: str = Field(min_length=1, max_length=100)
    terminal_id: str = Field(min_length=1, max_length=100)
    agent: str = Field(min_length=1, max_length=200)
    source_path: str = Field(min_length=1, max_length=4096)
    session_id: str = Field(min_length=1, max_length=200)
    baseline_input: int = Field(ge=0, strict=True)
    baseline_output: int = Field(ge=0, strict=True)
    progress: Optional[str] = Field(default=None, max_length=1024)
    enqueued_at: str = Field(min_length=1, max_length=100)


def _reconcile_dir() -> Path:
    from cli_agent_orchestrator.constants import CAO_HOME_DIR

    return CAO_HOME_DIR / "grok-usage-reconcile"


def _pending_path() -> Path:
    return _reconcile_dir() / "pending.jsonl"


def _lock_path() -> Path:
    return _reconcile_dir() / ".lock"


def _ttl_seconds() -> int:
    try:
        value = int(os.environ.get("CAO_GROK_RECONCILE_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS)))
    except ValueError:
        return _DEFAULT_TTL_SECONDS
    return max(60, value)


def _max_bytes() -> int:
    try:
        value = int(os.environ.get("CAO_GROK_RECONCILE_MAX_BYTES", str(_DEFAULT_MAX_BYTES)))
    except ValueError:
        return _DEFAULT_MAX_BYTES
    return max(1, value)


def _ensure_dir() -> Path:
    directory = _reconcile_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        logger.warning("Could not restrict Grok reconcile directory permissions")
    return directory


@contextmanager
def _locked() -> Iterator[None]:
    _ensure_dir()
    fd = os.open(str(_lock_path()), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_hints() -> list[GrokReconcileHint]:
    path = _pending_path()
    if not path.exists():
        return []
    hints: list[GrokReconcileHint] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            hints.append(GrokReconcileHint.model_validate_json(line))
        except ValidationError:
            logger.debug("Dropping malformed Grok reconcile hint")
    return hints


def _write_hints(hints: list[GrokReconcileHint]) -> None:
    path = _pending_path()
    if not hints:
        path.unlink(missing_ok=True)
        return
    body = "".join(hint.model_dump_json() + "\n" for hint in hints).encode("utf-8")
    tmp = path.with_suffix(".jsonl.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, body)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def enqueue_grok_usage_reconcile(
    *,
    record_id: str,
    terminal_id: str,
    agent: str,
    source_path: str,
    session_id: str,
    baseline_input: int,
    baseline_output: int,
    progress: Optional[str] = None,
) -> None:
    """Durably record one estimated Grok row for later native upgrade.

    Best-effort: a full or unwritable spool never breaks worker completion.
    """

    hint = GrokReconcileHint(
        record_id=record_id,
        terminal_id=terminal_id,
        agent=agent,
        source_path=source_path,
        session_id=session_id,
        baseline_input=baseline_input,
        baseline_output=baseline_output,
        progress=progress,
        enqueued_at=datetime.now(timezone.utc).isoformat(),
    )
    encoded = (hint.model_dump_json() + "\n").encode("utf-8")
    try:
        with _locked():
            pending = _pending_path()
            current = pending.stat().st_size if pending.exists() else 0
            if current + len(encoded) > _max_bytes():
                logger.warning("Grok reconcile spool size limit reached; hint dropped")
                return
            fd = os.open(str(pending), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, encoded)
                os.fsync(fd)
            finally:
                os.close(fd)
    except Exception:  # noqa: BLE001 — reconciliation must never break completion
        logger.debug("Failed to enqueue Grok usage reconcile hint for %s", terminal_id)


def _is_expired(hint: GrokReconcileHint, now: datetime, ttl: int) -> bool:
    try:
        enqueued = datetime.fromisoformat(hint.enqueued_at)
    except ValueError:
        return True
    if enqueued.tzinfo is None:
        enqueued = enqueued.replace(tzinfo=timezone.utc)
    return (now - enqueued).total_seconds() > ttl


def reconcile_pending_grok_usage() -> int:
    """Upgrade estimated Grok rows whose native usage has since flushed.

    Returns the number of rows upgraded in this pass. Hints that are still
    pending native evidence are retained; expired or already-resolved hints are
    dropped. A single writer (the daemon) holds the lock across read and
    rewrite, so enqueues from worker threads serialize cleanly against it.
    """

    from cli_agent_orchestrator.clients.database import (
        update_worker_token_usage_native,
    )
    from cli_agent_orchestrator.services.interactive_token_usage import (
        grok_native_usage_from_marker,
    )

    now = datetime.now(timezone.utc)
    ttl = _ttl_seconds()
    upgraded = 0

    with _locked():
        hints = _read_hints()
        if not hints:
            return 0
        remaining: list[GrokReconcileHint] = []
        for hint in hints:
            if _is_expired(hint, now, ttl):
                logger.debug(
                    "Grok reconcile hint for %s expired without native usage",
                    hint.terminal_id,
                )
                continue
            try:
                usage = grok_native_usage_from_marker(
                    source_path=Path(hint.source_path),
                    session_id=hint.session_id,
                    baseline_input=hint.baseline_input,
                    baseline_output=hint.baseline_output,
                    agent=hint.agent,
                    progress=hint.progress,
                )
            except Exception:  # noqa: BLE001 — one bad hint must not stall the pass
                logger.debug("Grok reconcile read failed for %s", hint.terminal_id)
                remaining.append(hint)
                continue
            if usage is None:
                remaining.append(hint)
                continue
            try:
                if update_worker_token_usage_native(hint.record_id, usage):
                    upgraded += 1
                    logger.info(
                        "Upgraded estimated Grok row %s to native (%d tokens)",
                        hint.record_id,
                        usage.total_tokens,
                    )
                # Row upgraded, or already non-estimated/gone: drop the hint.
            except Exception:  # noqa: BLE001 — retry on the next pass
                logger.debug("Grok reconcile update failed for %s", hint.record_id)
                remaining.append(hint)
        _write_hints(remaining)

    return upgraded
