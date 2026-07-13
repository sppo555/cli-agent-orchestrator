"""Durable fallback spool for worker token-usage records.

The spool is metadata-only. It is deliberately not a transcript or provider
session-log mirror: prompt, response, and raw provider output never enter the
payload. Writers and flushers share an advisory lock, complete lines are
replayed in order, and an incomplete tail is retained for the next process.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal, Mapping, Optional

import fcntl
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cli_agent_orchestrator.models.token_usage import TokenUsage

logger = logging.getLogger(__name__)

SPOOL_VERSION = 1
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024


class TokenUsageSpoolPayload(BaseModel):
    """Versioned, privacy-bounded payload stored in the fallback spool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = SPOOL_VERSION
    record_id: str = Field(min_length=1, max_length=100)
    recorded_at: str = Field(min_length=1, max_length=100)
    terminal_id: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    agent: str = Field(min_length=1, max_length=200)
    run_id: Optional[str] = Field(default=None, max_length=200)
    step_id: Optional[str] = Field(default=None, max_length=200)
    model: Optional[str] = Field(default=None, max_length=200)
    effort: Optional[str] = Field(default=None, max_length=100)
    progress: Optional[str] = Field(default=None, max_length=1024)
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    total_tokens: int = Field(ge=0, strict=True)
    estimated: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def validate_total(self) -> "TokenUsageSpoolPayload":
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        return self

    def to_usage(self) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.total_tokens,
            estimated=self.estimated,
            model=self.model,
            effort=self.effort,
            progress=self.progress,
        )


@dataclass(frozen=True)
class SpoolFlushResult:
    """Outcome of one bounded spool flush attempt."""

    flushed: int = 0
    malformed: int = 0
    failed: int = 0
    pending: int = 0
    pending_bytes: int = 0


_failure_count = 0
_malformed_count = 0
_flush_success_count = 0


def _spool_dir() -> Path:
    from cli_agent_orchestrator.constants import CAO_HOME_DIR

    return CAO_HOME_DIR / "token-usage-spool"


def _pending_path() -> Path:
    return _spool_dir() / "pending.jsonl"


def _lock_path() -> Path:
    return _spool_dir() / ".lock"


def _quarantine_path() -> Path:
    return _spool_dir() / "quarantine.jsonl"


def _max_bytes() -> int:
    try:
        value = int(os.environ.get("CAO_TOKEN_USAGE_SPOOL_MAX_BYTES", str(_DEFAULT_MAX_BYTES)))
    except ValueError:
        return _DEFAULT_MAX_BYTES
    return max(1, value)


def _ensure_spool_dir() -> Path:
    directory = _spool_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        logger.warning("Could not restrict token usage spool directory permissions")
    return directory


@contextmanager
def _locked() -> Iterator[None]:
    _ensure_spool_dir()
    fd = os.open(str(_lock_path()), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            os.chmod(_lock_path(), 0o600)
        except OSError:
            logger.warning("Could not restrict token usage spool lock permissions")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def build_spool_payload(
    *,
    terminal_id: str,
    provider: str,
    agent: str,
    usage: TokenUsage,
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
    progress: Optional[str] = None,
    record_id: Optional[str] = None,
    recorded_at: Optional[str] = None,
) -> TokenUsageSpoolPayload:
    """Build the only payload shape accepted by the durable spool."""

    return TokenUsageSpoolPayload(
        record_id=record_id or str(uuid.uuid4()),
        recorded_at=recorded_at or datetime.now(timezone.utc).isoformat(),
        terminal_id=terminal_id,
        provider=provider,
        agent=agent,
        run_id=run_id,
        step_id=step_id,
        model=usage.model,
        effort=usage.effort,
        progress=progress if progress is not None else usage.progress,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        estimated=usage.estimated,
    )


def append_token_usage_spool(payload: TokenUsageSpoolPayload | Mapping[str, Any]) -> None:
    """Atomically append one metadata payload and fsync it.

    A short/partial write is never silently repaired or overwritten. The
    incomplete tail remains visible to the next flush and blocks subsequent
    appends until it is handled, preserving the no-loss invariant.
    """

    global _failure_count
    model = (
        payload
        if isinstance(payload, TokenUsageSpoolPayload)
        else TokenUsageSpoolPayload.model_validate(payload)
    )
    encoded = (model.model_dump_json() + "\n").encode("utf-8")
    try:
        with _locked():
            pending = _pending_path()
            if pending.exists() and pending.stat().st_size:
                with pending.open("rb") as existing:
                    existing.seek(-1, os.SEEK_END)
                    if existing.read(1) != b"\n":
                        raise OSError("token usage spool has an incomplete tail")
            current_size = pending.stat().st_size if pending.exists() else 0
            if current_size + len(encoded) > _max_bytes():
                raise OSError("token usage spool size limit reached; unacked item retained")
            fd = os.open(str(pending), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                written = os.write(fd, encoded)
                if written != len(encoded):
                    raise OSError("token usage spool append was partial")
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.chmod(pending, 0o600)
            except OSError:
                logger.warning("Could not restrict token usage spool file permissions")
    except Exception:
        _failure_count += 1
        raise


def _quarantine(raw_line: bytes, reason: str) -> None:
    quarantine = _quarantine_path()
    entry = json.dumps(
        {
            "version": SPOOL_VERSION,
            "reason": reason[:500],
            "raw_line": raw_line.decode("utf-8", errors="replace").rstrip("\n"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    fd = os.open(str(quarantine), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = os.write(fd, entry)
        if written != len(entry):
            raise OSError("token usage quarantine append was partial")
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.chmod(quarantine, 0o600)
    except OSError:
        logger.warning("Could not restrict token usage quarantine permissions")


def _rewrite_pending(lines: list[bytes]) -> None:
    pending = _pending_path()
    temporary = pending.with_name("pending.jsonl.tmp")
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        for line in lines:
            written = os.write(fd, line)
            if written != len(line):
                raise OSError("token usage spool rewrite was partial")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, pending)
    try:
        os.chmod(pending, 0o600)
    except OSError:
        logger.warning("Could not restrict token usage spool permissions after rewrite")


def flush_token_usage_spool(*, max_items: Optional[int] = None) -> SpoolFlushResult:
    """Replay complete spool lines; retain DB failures and incomplete tails."""

    global _malformed_count, _flush_success_count, _failure_count
    from cli_agent_orchestrator.clients.database import record_worker_token_usage

    if max_items is not None and max_items < 1:
        raise ValueError("max_items must be greater than zero")
    flushed = malformed = failed = 0
    with _locked():
        pending = _pending_path()
        if not pending.exists():
            return SpoolFlushResult()
        raw = pending.read_bytes()
        lines = raw.splitlines(keepends=True)
        complete = lines
        tail: list[bytes] = []
        if lines and not lines[-1].endswith(b"\n"):
            complete = lines[:-1]
            tail = [lines[-1]]
        remaining = list(tail)
        for index, raw_line in enumerate(complete):
            if max_items is not None and flushed >= max_items:
                remaining.extend(complete[index:])
                break
            try:
                payload = TokenUsageSpoolPayload.model_validate_json(raw_line)
            except Exception as exc:
                _quarantine(raw_line, str(exc))
                malformed += 1
                _malformed_count += 1
                continue
            try:
                record_worker_token_usage(
                    terminal_id=payload.terminal_id,
                    provider=payload.provider,
                    agent=payload.agent,
                    run_id=payload.run_id,
                    step_id=payload.step_id,
                    usage=payload.to_usage(),
                    progress=payload.progress,
                    record_id=payload.record_id,
                    recorded_at=payload.recorded_at,
                )
            except Exception:
                failed += 1
                _failure_count += 1
                remaining.extend(complete[index:])
                break
            flushed += 1
            _flush_success_count += 1
        if flushed or malformed:
            _rewrite_pending(remaining)
        pending_count = len(remaining)
        pending_bytes = sum(len(line) for line in remaining)
    return SpoolFlushResult(
        flushed=flushed,
        malformed=malformed,
        failed=failed,
        pending=pending_count,
        pending_bytes=pending_bytes,
    )


def token_usage_spool_metrics() -> dict[str, Any]:
    """Return observable spool metrics without deleting or acknowledging data."""

    with _locked():
        pending = _pending_path()
        raw = pending.read_bytes() if pending.exists() else b""
    lines = raw.splitlines(keepends=True)
    complete = [line for line in lines if line.endswith(b"\n")]
    oldest_age: Optional[float] = None
    for line in complete:
        try:
            recorded_at = TokenUsageSpoolPayload.model_validate_json(line).recorded_at
            timestamp = datetime.fromisoformat(recorded_at.replace("Z", "+00:00")).timestamp()
            age = max(0.0, time.time() - timestamp)
            oldest_age = age if oldest_age is None else max(oldest_age, age)
        except Exception:
            continue
    return {
        "pending_count": len(lines),
        "pending_bytes": len(raw),
        "oldest_age_seconds": oldest_age,
        "failure_count": _failure_count,
        "malformed_count": _malformed_count,
        "flush_success_count": _flush_success_count,
        "over_limit": len(raw) > _max_bytes(),
    }
