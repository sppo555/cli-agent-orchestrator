import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli_agent_orchestrator.services import interactive_token_usage as interactive


def _write(path: Path, *events: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def _claude_event(message_id: str, *, uncached: int, created: int, read: int, output: int):
    return {
        "type": "assistant",
        "message": {
            "id": message_id,
            "model": "claude-sonnet-5",
            "usage": {
                "input_tokens": uncached,
                "cache_creation_input_tokens": created,
                "cache_read_input_tokens": read,
                "output_tokens": output,
            },
        },
    }


def _codex_event(input_tokens: int, output_tokens: int):
    return {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": max(0, input_tokens - 10),
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }
            },
        },
    }


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while value >= 0x80:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _protobuf_varint(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _protobuf_bytes(field: int, value: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(value)) + value


def _agy_metadata(input_tokens: int, output_tokens: int) -> bytes:
    # Sanitized Agy 1.1.x trajectory wrapper. No prompt/response payload exists
    # in this fixture; only GenerationMetadata token counters are represented.
    generation = b"".join(
        (
            _protobuf_varint(1, 123),  # provider latency; schema discriminator
            _protobuf_varint(2, input_tokens),
            _protobuf_varint(3, output_tokens),
            _protobuf_varint(6, 24),  # provider model enum; schema discriminator
        )
    )
    return _protobuf_bytes(1, _protobuf_bytes(4, generation))


def _agy_database(path: Path, *rows: tuple[int, bytes]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB)")
        connection.executemany("INSERT INTO gen_metadata(idx, data) VALUES (?, ?)", rows)


def test_claude_interactive_turn_sums_cache_input_and_deduplicates_messages(tmp_path):
    log = tmp_path / "claude.jsonl"
    _write(log, _claude_event("before", uncached=1, created=2, read=3, output=4))

    with patch.object(interactive, "_claude_source_path", return_value=log):
        assert interactive.begin_interactive_usage_turn(
            terminal_id="claude-1",
            provider="claude_code",
            agent="developer_claude",
            session_name="session",
            window_name="window",
            prompt="write .cao/worker-results/result.md",
        )

        first = _claude_event("msg-1", uncached=2, created=30, read=400, output=5)
        _write(
            log,
            first,
            first,  # Claude can journal the same API message more than once.
            _claude_event("msg-2", uncached=3, created=40, read=500, output=6),
        )
        assert interactive.observe_interactive_usage_processing("claude-1")
        turn = interactive.claim_completed_interactive_usage_turn("claude-1")
        assert turn is not None
        with patch.object(interactive, "persist_worker_token_usage") as persist:
            usage = interactive.complete_interactive_usage_turn(turn)

    assert usage is not None
    assert usage.input_tokens == 975
    assert usage.output_tokens == 11
    assert usage.total_tokens == 986
    assert usage.estimated is False
    assert usage.model == "claude-sonnet-5"
    assert usage.progress == ".cao/worker-results/result.md"
    persist.assert_called_once()


def test_codex_interactive_turn_persists_cumulative_delta(tmp_path):
    log = tmp_path / "rollout-test.jsonl"
    _write(log, _codex_event(100, 5))

    with patch.object(interactive, "_discover_codex_rollout", return_value=log):
        assert interactive.begin_interactive_usage_turn(
            terminal_id="codex-1",
            provider="codex",
            agent="developer_codex",
            session_name="session",
            window_name="window",
            prompt="do the task",
        )
        _write(log, _codex_event(170, 14))
        assert interactive.observe_interactive_usage_processing("codex-1")
        turn = interactive.claim_completed_interactive_usage_turn("codex-1")
        assert turn is not None
        with (
            patch.object(interactive, "persist_worker_token_usage") as persist,
            patch.object(
                interactive, "resolve_worker_configuration", return_value=("gpt-5", "xhigh")
            ),
        ):
            usage = interactive.complete_interactive_usage_turn(turn)

    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (70, 9, 79)
    assert usage.estimated is False
    assert usage.model == "gpt-5"
    assert usage.effort == "xhigh"
    persist.assert_called_once()


@pytest.mark.parametrize(
    "model",
    [
        "Claude Sonnet 4.6 (Thinking)",
        "Claude Opus 4.6 (Thinking)",
        "Gemini 3.1 Pro (High)",
        "Gemini 3.5 Flash (Low)",
    ],
)
def test_agy_interactive_turn_sums_native_generations_after_marker(tmp_path, model):
    database = tmp_path / "conversation.db"
    _agy_database(database, (0, _agy_metadata(100, 5)))
    terminal_id = f"agy-{model}"

    with patch.object(interactive, "_discover_agy_conversation", return_value=database):
        assert interactive.begin_interactive_usage_turn(
            terminal_id=terminal_id,
            provider="antigravity_cli",
            agent="developer_agy",
            session_name="session",
            window_name="window",
            prompt="do the task",
        )
        with sqlite3.connect(database) as connection:
            connection.executemany(
                "INSERT INTO gen_metadata(idx, data) VALUES (?, ?)",
                [(1, _agy_metadata(200, 11)), (2, _agy_metadata(300, 17))],
            )
        assert interactive.observe_interactive_usage_processing(terminal_id)
        turn = interactive.claim_completed_interactive_usage_turn(terminal_id)
        assert turn is not None
        with (
            patch.object(interactive, "persist_worker_token_usage") as persist,
            patch.object(
                interactive,
                "resolve_worker_configuration",
                return_value=(model, None),
            ),
        ):
            usage = interactive.complete_interactive_usage_turn(turn)

    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (500, 28, 528)
    assert usage.estimated is False
    assert usage.model == model
    persist.assert_called_once()


def test_agy_malformed_metadata_is_ignored_without_reading_payload(tmp_path):
    database = tmp_path / "conversation.db"
    _agy_database(
        database,
        (0, _agy_metadata(10, 2)),
        (1, b"prompt and response bytes that are not protobuf"),
        (2, _protobuf_bytes(1, _protobuf_bytes(4, _protobuf_varint(2, 99)))),
    )
    assert interactive._agy_totals_after(database, 0) is None


def test_agy_missing_source_falls_back_instead_of_claiming_native_turn():
    with patch.object(interactive, "_discover_agy_conversation", return_value=None):
        assert not interactive.begin_interactive_usage_turn(
            terminal_id="agy-missing",
            provider="antigravity_cli",
            agent="developer_agy",
            session_name="session",
            window_name="window",
            prompt="task",
        )
    assert interactive.claim_completed_interactive_usage_turn("agy-missing") is None


def test_agy_conversation_is_correlated_by_terminal_specific_working_directory(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    cache = home / ".gemini" / "antigravity-cli" / "cache"
    conversations = home / ".gemini" / "antigravity-cli" / "conversations"
    cache.mkdir(parents=True)
    conversations.mkdir(parents=True)
    expected = conversations / "conversation-1.db"
    expected.touch()
    (cache / "last_conversations.json").write_text(
        json.dumps({"/tmp/agy-workspaces/terminal-1": "conversation-1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    with patch.object(
        interactive,
        "_pane_working_directory",
        return_value="/tmp/agy-workspaces/terminal-1",
    ):
        assert interactive._discover_agy_conversation("session", "window") == expected


def test_second_input_while_busy_does_not_reset_native_baseline(tmp_path):
    log = tmp_path / "rollout-test.jsonl"
    _write(log, _codex_event(10, 2))
    with patch.object(interactive, "_discover_codex_rollout", return_value=log):
        assert interactive.begin_interactive_usage_turn(
            terminal_id="codex-busy",
            provider="codex",
            agent="developer",
            session_name="session",
            window_name="window",
            prompt="first",
        )
        assert not interactive.begin_interactive_usage_turn(
            terminal_id="codex-busy",
            provider="codex",
            agent="developer",
            session_name="session",
            window_name="window",
            prompt="queued second",
        )
    interactive.clear_interactive_usage_terminal("codex-busy")


def test_unknown_provider_is_not_claimed():
    assert not interactive.begin_interactive_usage_turn(
        terminal_id="kiro-1",
        provider="kiro_cli",
        agent="developer",
        session_name="session",
        window_name="window",
        prompt="task",
    )
    assert interactive.claim_completed_interactive_usage_turn("kiro-1") is None


def test_stale_ready_edge_cannot_claim_before_new_processing(tmp_path):
    log = tmp_path / "rollout-test.jsonl"
    _write(log, _codex_event(10, 2))
    with patch.object(interactive, "_discover_codex_rollout", return_value=log):
        assert interactive.begin_interactive_usage_turn(
            terminal_id="codex-race",
            provider="codex",
            agent="developer",
            session_name="session",
            window_name="window",
            prompt="task",
        )

    assert interactive.claim_completed_interactive_usage_turn("codex-race") is None
    assert interactive.observe_interactive_usage_processing("codex-race")
    assert interactive.claim_completed_interactive_usage_turn("codex-race") is not None
    interactive.clear_interactive_usage_terminal("codex-race")


def test_zero_delta_releases_claim_and_real_completion_consumes_marker(tmp_path):
    log = tmp_path / "rollout-test.jsonl"
    _write(log, _codex_event(100, 5))
    with patch.object(interactive, "_discover_codex_rollout", return_value=log):
        assert interactive.begin_interactive_usage_turn(
            terminal_id="codex-premature",
            provider="codex",
            agent="developer",
            session_name="session",
            window_name="window",
            prompt="task",
        )
    assert interactive.observe_interactive_usage_processing("codex-premature")

    premature = interactive.claim_completed_interactive_usage_turn("codex-premature")
    assert premature is not None
    assert interactive.claim_completed_interactive_usage_turn("codex-premature") is None
    with (
        patch.object(interactive, "persist_worker_token_usage") as persist,
        patch.object(interactive, "_CAPTURE_RETRY_DELAYS", (0.0,)),
    ):
        assert interactive.complete_interactive_usage_turn(premature) is None
        persist.assert_not_called()

        _write(log, _codex_event(175, 14))
        completed = interactive.claim_completed_interactive_usage_turn("codex-premature")
        assert completed is premature
        usage = interactive.complete_interactive_usage_turn(completed)

    assert usage is not None
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (75, 9, 84)
    assert interactive.claim_completed_interactive_usage_turn("codex-premature") is None
    persist.assert_called_once()


def test_terminal_finalize_flushes_active_turn_without_another_status_edge(tmp_path):
    log = tmp_path / "claude.jsonl"
    log.touch()
    with patch.object(interactive, "_claude_source_path", return_value=log):
        assert interactive.begin_interactive_usage_turn(
            terminal_id="claude-delete",
            provider="claude_code",
            agent="reviewer",
            session_name="session",
            window_name="window",
            prompt="review",
        )
        _write(log, _claude_event("done", uncached=3, created=20, read=300, output=9))
        with patch.object(interactive, "persist_worker_token_usage") as persist:
            usage = interactive.finalize_interactive_usage_terminal("claude-delete")

    assert usage is not None
    assert usage.total_tokens == 332
    persist.assert_called_once()
    assert interactive.claim_completed_interactive_usage_turn("claude-delete") is None


def test_codex_source_is_correlated_from_pane_process_open_file(tmp_path):
    rollout = tmp_path / "rollout-worker.jsonl"
    rollout.touch()
    pane_result = MagicMock(stdout="100\n")
    ps_result = MagicMock(stdout="100 1\n200 100\n")
    lsof_result = MagicMock(stdout=f"p200\nfcwd\nn{rollout}\n")
    with patch.object(
        interactive.subprocess,
        "run",
        side_effect=[pane_result, ps_result, lsof_result],
    ):
        assert interactive._discover_codex_rollout("cao-project", "developer-1") == rollout


def test_missing_provider_usage_omits_record_instead_of_inventing_estimate(tmp_path):
    log = tmp_path / "rollout-empty.jsonl"
    log.touch()
    turn = interactive.InteractiveUsageTurn(
        terminal_id="codex-empty",
        provider="codex",
        agent="developer",
        session_name="session",
        window_name="window",
        progress=None,
        source_path=log,
        marker=None,
    )
    with (
        patch.object(interactive, "persist_worker_token_usage") as persist,
        patch.object(interactive, "_CAPTURE_RETRY_DELAYS", (0.0,)),
    ):
        assert interactive.complete_interactive_usage_turn(turn) is None
    persist.assert_not_called()
