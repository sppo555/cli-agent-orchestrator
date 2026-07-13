import json
import os
import stat
from unittest.mock import patch

import pytest

from cli_agent_orchestrator.models.token_usage import TokenUsage
from cli_agent_orchestrator.services import token_usage_spool as spool
from cli_agent_orchestrator.services.token_usage import persist_worker_token_usage


def _usage(*, estimated=True):
    return TokenUsage(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        estimated=estimated,
        model="claude-sonnet",
        effort="high",
        progress=".cao/worker-results/result.md",
    )


def _payload(*, record_id="record-1", estimated=True):
    return spool.build_spool_payload(
        terminal_id="abc12345",
        provider="claude_code",
        agent="reviewer",
        usage=_usage(estimated=estimated),
        run_id="run-1",
        step_id="step-1",
        record_id=record_id,
        recorded_at="2026-07-13T00:00:00+00:00",
    )


@pytest.fixture
def spool_home(tmp_path, monkeypatch):
    monkeypatch.setattr("cli_agent_orchestrator.constants.CAO_HOME_DIR", tmp_path)
    return tmp_path


def test_payload_is_metadata_only_and_rejects_transcript_fields():
    payload = _payload()
    encoded = payload.model_dump_json()
    assert "prompt" not in encoded
    assert "response" not in encoded
    assert "transcript" not in encoded
    with pytest.raises(ValueError):
        spool.TokenUsageSpoolPayload.model_validate(
            {**payload.model_dump(), "prompt": "do not store this"}
        )
    with pytest.raises(ValueError):
        spool.TokenUsageSpoolPayload.model_validate(
            {**payload.model_dump(), "input_tokens": "10"}
        )


def test_append_fsyncs_owner_only_spool_and_exposes_metrics(spool_home):
    with patch.object(spool.os, "fsync") as fsync:
        spool.append_token_usage_spool(_payload())
    fsync.assert_called_once()

    pending = spool_home / "token-usage-spool" / "pending.jsonl"
    assert pending.exists()
    assert stat.S_IMODE(pending.stat().st_mode) == 0o600
    assert stat.S_IMODE(pending.parent.stat().st_mode) == 0o700
    metrics = spool.token_usage_spool_metrics()
    assert metrics["pending_count"] == 1
    assert metrics["pending_bytes"] == pending.stat().st_size
    assert metrics["oldest_age_seconds"] is not None


def test_flush_replays_and_duplicate_record_id_is_idempotent(spool_home, monkeypatch):
    import sqlite3

    from cli_agent_orchestrator.clients.database import (
        _migrate_worker_token_usage,
        list_worker_token_usage,
        record_worker_token_usage,
    )

    db_file = spool_home / "usage.db"
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_file)
    _migrate_worker_token_usage()
    payload = _payload()
    spool.append_token_usage_spool(payload)

    result = spool.flush_token_usage_spool()
    assert result.flushed == 1
    assert result.pending == 0
    assert spool.flush_token_usage_spool().flushed == 0

    # A crash after DB commit but before spool rewrite must not create a
    # second durable row when the same payload is replayed.
    record_worker_token_usage(
        terminal_id=payload.terminal_id,
        provider=payload.provider,
        agent=payload.agent,
        usage=payload.to_usage(),
        run_id=payload.run_id,
        step_id=payload.step_id,
        progress=payload.progress,
        record_id=payload.record_id,
        recorded_at=payload.recorded_at,
    )
    assert len(list_worker_token_usage()) == 1
    with sqlite3.connect(str(db_file)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM worker_token_usage").fetchone()[0] == 1


def test_database_failure_retains_all_unacknowledged_items(spool_home):
    spool.append_token_usage_spool(_payload(record_id="record-1"))
    spool.append_token_usage_spool(_payload(record_id="record-2"))
    with patch(
        "cli_agent_orchestrator.clients.database.record_worker_token_usage",
        side_effect=OSError("sqlite unavailable"),
    ):
        result = spool.flush_token_usage_spool()

    assert result.flushed == 0
    assert result.failed == 1
    assert result.pending == 2
    assert spool.token_usage_spool_metrics()["pending_count"] == 2


def test_malformed_item_is_quarantined_without_blocking_following_item(spool_home):
    pending = spool_home / "token-usage-spool" / "pending.jsonl"
    pending.parent.mkdir(mode=0o700)
    pending.write_bytes(b"{malformed json}\n" + (_payload().model_dump_json() + "\n").encode())

    with patch("cli_agent_orchestrator.clients.database.record_worker_token_usage") as record:
        result = spool.flush_token_usage_spool()

    assert result.malformed == 1
    assert result.flushed == 1
    record.assert_called_once()
    quarantine = pending.parent / "quarantine.jsonl"
    assert quarantine.exists()
    assert "malformed json" in quarantine.read_text()


def test_unknown_version_is_quarantined_without_blocking_following_item(spool_home):
    pending = spool_home / "token-usage-spool" / "pending.jsonl"
    pending.parent.mkdir(mode=0o700)
    unknown = {**_payload().model_dump(), "version": 99}
    pending.write_bytes(
        (
            json.dumps(unknown)
            + "\n"
            + _payload(record_id="record-2").model_dump_json()
            + "\n"
        ).encode()
    )

    with patch("cli_agent_orchestrator.clients.database.record_worker_token_usage") as record:
        result = spool.flush_token_usage_spool()

    assert result.malformed == 1
    assert result.flushed == 1
    record.assert_called_once()
    assert "literal_error" in (pending.parent / "quarantine.jsonl").read_text()


def test_incomplete_tail_is_retained_and_not_appended_over(spool_home):
    pending = spool_home / "token-usage-spool" / "pending.jsonl"
    pending.parent.mkdir(mode=0o700)
    pending.write_bytes(b'{"version":1,"record_id":"partial"')

    result = spool.flush_token_usage_spool()
    assert result.flushed == 0
    assert result.pending == 1
    assert result.pending_bytes == pending.stat().st_size
    with pytest.raises(OSError, match="incomplete tail"):
        spool.append_token_usage_spool(_payload())


def test_size_limit_rejects_new_item_without_deleting_unacked_item(spool_home, monkeypatch):
    spool.append_token_usage_spool(_payload())
    pending = spool_home / "token-usage-spool" / "pending.jsonl"
    before = pending.read_bytes()
    monkeypatch.setenv("CAO_TOKEN_USAGE_SPOOL_MAX_BYTES", str(len(before)))

    with pytest.raises(OSError, match="size limit"):
        spool.append_token_usage_spool(_payload(record_id="record-2"))
    assert pending.read_bytes() == before


def test_partial_os_write_leaves_visible_tail_instead_of_silent_loss(spool_home):
    def partial_write(fd, data):
        return max(1, len(data) - 1)

    with patch.object(spool.os, "write", side_effect=partial_write):
        with pytest.raises(OSError, match="partial"):
            spool.append_token_usage_spool(_payload())

    pending = spool_home / "token-usage-spool" / "pending.jsonl"
    assert pending.exists()
    assert not pending.read_bytes().endswith(b"\n")


def test_fsync_failure_keeps_written_item_visible(spool_home):
    with patch.object(spool.os, "fsync", side_effect=OSError("fsync unavailable")):
        with pytest.raises(OSError, match="fsync unavailable"):
            spool.append_token_usage_spool(_payload())

    pending = spool_home / "token-usage-spool" / "pending.jsonl"
    assert pending.exists()
    assert pending.read_bytes().endswith(b"\n")


def test_file_write_failure_does_not_fail_worker_completion(spool_home):
    with patch.object(spool, "append_token_usage_spool", side_effect=PermissionError("read-only")):
        persist_worker_token_usage(
            terminal_id="abc12345",
            provider="codex",
            agent="developer",
            usage=_usage(),
            run_id="run-1",
            step_id="step-1",
        )

    pending = spool_home / "token-usage-spool" / "pending.jsonl"
    assert not pending.exists()


def test_persist_falls_back_to_spool_without_failing_worker(spool_home):
    with (
        patch(
            "cli_agent_orchestrator.clients.database.record_worker_token_usage",
            side_effect=OSError("sqlite unavailable"),
        ),
        patch.object(spool, "append_token_usage_spool") as append,
    ):
        persist_worker_token_usage(
            terminal_id="abc12345",
            provider="codex",
            agent="developer",
            usage=_usage(),
            run_id="run-1",
            step_id="step-1",
        )

    append.assert_called_once()
    payload = append.call_args.args[0]
    assert payload.provider == "codex"
    assert payload.total_tokens == 15
    assert not hasattr(payload, "prompt")
