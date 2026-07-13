import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
