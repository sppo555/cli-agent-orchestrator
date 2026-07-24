"""Unit tests for the Grok CLI lifecycle provider."""

import re
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.grok_cli import (
    _GROK_VERSION_CACHE,
    MAX_COMMAND_BYTES,
    STARTUP_GUARD,
    GrokCliProvider,
    _probe_grok_version,
)
from cli_agent_orchestrator.services.interactive_token_usage import grok_usage_session_id


def make_provider(**kwargs) -> GrokCliProvider:
    return GrokCliProvider("terminal1", "session1", "window1", **kwargs)


FIXTURES = Path(__file__).parent / "fixtures" / "grok_cli"
RENDER_PYTE = runpy.run_path(str(FIXTURES / "render_with_pyte.py"))["render"]


def load_raw_fixture(name: str) -> str:
    return (FIXTURES / "raw" / f"{name}.ansi").read_text()


def load_screen_fixture(name: str) -> list[str]:
    return (FIXTURES / "rendered_pyte" / f"{name}.txt").read_text().splitlines()


@pytest.mark.parametrize(
    "expected_path",
    sorted((FIXTURES / "rendered_pyte").glob("*.txt")),
    ids=lambda path: path.stem,
)
def test_sanitized_raw_reproduces_rendered_pyte(expected_path, tmp_path):
    source = FIXTURES / "raw" / f"{expected_path.stem}.ansi"
    actual = tmp_path / expected_path.name
    assert source.exists()
    RENDER_PYTE(source, actual, columns=120, rows=40)
    assert actual.read_text() == expected_path.read_text()


def test_constructor_contract():
    provider = make_provider()
    assert provider.paste_enter_count == 1
    assert provider.paste_submit_delay == 0.8
    assert provider.blocks_orchestrated_input_while_waiting_user_answer is True
    assert provider.supports_screen_detection is True
    assert provider._turns == 0
    assert provider._initialized is False


def test_registration_sets_are_consistent():
    from cli_agent_orchestrator.cli.commands.launch import (
        PROVIDERS_REQUIRING_WORKSPACE_ACCESS,
    )
    from cli_agent_orchestrator.models.provider import ProviderType
    from cli_agent_orchestrator.services.terminal_service import (
        RUNTIME_SKILL_PROMPT_PROVIDERS,
        SOFT_ENFORCEMENT_PROVIDERS,
    )

    assert ProviderType.GROK_CLI.value == "grok_cli"
    assert "grok_cli" in PROVIDERS_REQUIRING_WORKSPACE_ACCESS
    assert "grok_cli" in RUNTIME_SKILL_PROMPT_PROVIDERS
    assert "grok_cli" not in SOFT_ENFORCEMENT_PROVIDERS


def test_command_requires_binary():
    with patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="not on PATH"):
            make_provider()._build_grok_command()


def test_basic_command_uses_resolved_binary():
    with patch(
        "cli_agent_orchestrator.providers.grok_cli.shutil.which",
        return_value="/opt/grok/bin/grok",
    ):
        command = make_provider()._build_grok_command()
    assert command.startswith("/opt/grok/bin/grok --always-approve --session-id ")
    assert grok_usage_session_id("terminal1", "session1", "window1") in command
    assert "Acknowledge your role briefly" in command
    assert "Do not inspect, edit, execute" in command
    assert "--plugin-dir" not in command


def test_constructor_model_is_forwarded():
    with patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"):
        command = make_provider(model="grok-4.5")._build_grok_command()
    assert "--model grok-4.5" in command


def test_build_structured_command_uses_attempt_local_streaming_json_without_startup_guard():
    with (
        patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"),
        patch("cli_agent_orchestrator.providers.grok_cli.uuid.uuid4", return_value="attempt-id"),
    ):
        command = make_provider().build_structured_command()

    assert command[0] == "/bin/grok"
    assert grok_usage_session_id("terminal1", "session1", "window1") not in command
    assert command[-5:] == [
        "--output-format",
        "streaming-json",
        "--session-id",
        "attempt-id",
        "--single",
    ]
    assert [*command, "do it"][-2:] == ["--single", "do it"]
    assert STARTUP_GUARD not in command[command.index("--rules") + 1]


def test_profile_model_precedes_constructor_model():
    profile = AgentProfile(name="reviewer", description="Review", model="profile-model")
    with (
        patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"),
        patch(
            "cli_agent_orchestrator.providers.grok_cli.load_agent_profile",
            return_value=profile,
        ),
    ):
        command = make_provider(
            agent_profile="reviewer", model="constructor-model"
        )._build_grok_command()
    assert "profile-model" in command
    assert "constructor-model" not in command


def test_upstream_profile_without_effort_omits_flag():
    profile = AgentProfile(name="reviewer", description="Review")
    with (
        patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"),
        patch(
            "cli_agent_orchestrator.providers.grok_cli.load_agent_profile",
            return_value=profile,
        ),
    ):
        command = make_provider(agent_profile="reviewer")._build_grok_command()
    assert "--effort" not in command


def test_custom_profile_effort_is_forwarded():
    profile = SimpleNamespace(
        model=None,
        effort="high",
        system_prompt=None,
        mcpServers=None,
    )
    with (
        patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"),
        patch(
            "cli_agent_orchestrator.providers.grok_cli.load_agent_profile",
            return_value=profile,
        ),
    ):
        command = make_provider(agent_profile="custom")._build_grok_command()
    assert "--effort high" in command


def test_rules_include_profile_skills_security_and_guard():
    profile = AgentProfile(name="reviewer", description="Review", system_prompt="Review carefully.")
    with (
        patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"),
        patch(
            "cli_agent_orchestrator.providers.grok_cli.load_agent_profile",
            return_value=profile,
        ),
    ):
        command = make_provider(
            agent_profile="reviewer",
            skill_prompt="## Available Skills\n- inspect",
            allowed_tools=["fs_read", "fs_list"],
        )._build_grok_command()
    assert "--rules" in command
    assert "Review carefully." in command
    assert "Available Skills" in command
    assert "Do not inspect, edit, execute" in command
    assert "--deny Bash" in command
    assert "--deny Edit" in command
    assert "--no-subagents" in command


def test_bash_allowed_keeps_subagents_but_still_denies_write():
    with patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"):
        command = make_provider(
            allowed_tools=["execute_bash", "fs_read", "fs_list"]
        )._build_grok_command()
    assert "--no-subagents" not in command
    assert "--deny Edit" in command
    assert "--deny Bash" not in command


def test_wildcard_has_no_native_restrictions():
    with patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"):
        command = make_provider(allowed_tools=["*"])._build_grok_command()
    assert "--deny" not in command
    assert "--no-subagents" not in command


def test_profile_mcp_servers_only_warn(caplog):
    profile = AgentProfile(
        name="worker",
        description="Worker",
        mcpServers={"cao-mcp-server": {"command": "cao-mcp-server"}},
    )
    with (
        patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"),
        patch(
            "cli_agent_orchestrator.providers.grok_cli.load_agent_profile",
            return_value=profile,
        ),
    ):
        command = make_provider(agent_profile="worker")._build_grok_command()
    assert "mcp" not in command.lower()
    assert "does not copy profile MCP servers" in caplog.text


def test_cao_mcp_capability_marker_warns_but_does_not_add_config(caplog):
    with patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"):
        command = make_provider(
            allowed_tools=["fs_read", "fs_list", "@cao-mcp-server"]
        )._build_grok_command()
    assert "cao-mcp-server" not in command
    assert "lifecycle-only mode ignores" in caplog.text


def test_long_rules_fail_without_truncation():
    huge = "x" * MAX_COMMAND_BYTES
    profile = AgentProfile(name="large", description="Large", system_prompt=huge)
    with (
        patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"),
        patch(
            "cli_agent_orchestrator.providers.grok_cli.load_agent_profile",
            return_value=profile,
        ),
    ):
        with pytest.raises(ValueError, match="inline-rules limit"):
            make_provider(agent_profile="large")._build_grok_command()


def test_version_probe_is_cached_by_binary_path():
    _GROK_VERSION_CACHE.clear()
    completed = SimpleNamespace(returncode=0, stdout="grok 0.2.101 (build)\n")
    with patch(
        "cli_agent_orchestrator.providers.grok_cli.subprocess.run", return_value=completed
    ) as run:
        assert _probe_grok_version("/bin/grok") == "grok 0.2.101 (build)"
        assert _probe_grok_version("/bin/grok") == "grok 0.2.101 (build)"
    run.assert_called_once()


PROCESSING_SCREEN = [
    "⠧ Starting session… 1.0s",
    "│ ❯                                      │",
    "╰──────────── Grok 4.5 (high) · always-approve ─╯",
]


@pytest.mark.parametrize(
    ("name", "expected", "turns"),
    [
        ("shell_prompt", TerminalStatus.UNKNOWN, 0),
        ("startup", TerminalStatus.IDLE, 0),
        ("idle_capture_pane", TerminalStatus.IDLE, 0),
        ("processing_capture_pane", TerminalStatus.PROCESSING, 1),
        ("completed_capture_pane", TerminalStatus.COMPLETED, 1),
        ("waiting_question_after", TerminalStatus.WAITING_USER_ANSWER, 1),
        ("plan_after", TerminalStatus.COMPLETED, 1),
        ("markdown_processing", TerminalStatus.PROCESSING, 1),
        ("markdown_completed", TerminalStatus.COMPLETED, 1),
        # Despite its historical filename, this capture still contains an
        # active Responding/[stop] surface and is therefore processing.
        ("long_response_completed", TerminalStatus.PROCESSING, 1),
    ],
)
def test_phase0_raw_and_pyte_status_fixtures(name, expected, turns):
    provider = make_provider()
    for _ in range(turns):
        provider.mark_input_received()
    assert provider.get_status(load_raw_fixture(name)) == expected
    assert provider.get_status_from_screen(load_screen_fixture(name)) == expected


def test_ready_surface_allows_pyte_line_wrapping():
    provider = make_provider()
    provider.mark_input_received()
    wrapped = ["│ ❯", "│", "G", "rok 4.5 (high) · always-", "approve"]
    assert provider.get_status_from_screen(wrapped) == TerminalStatus.COMPLETED


def test_stale_processing_marker_does_not_override_newer_completion():
    provider = make_provider()
    provider.mark_input_received()
    raw = (FIXTURES / "regressions" / "stale_processing_raw.txt").read_text()
    screen = (FIXTURES / "regressions" / "stale_processing_screen.txt").read_text()
    assert provider.get_status(raw) == TerminalStatus.COMPLETED
    assert provider.get_status_from_screen(screen.splitlines()) == TerminalStatus.COMPLETED


def test_stale_ready_marker_does_not_override_new_processing():
    provider = make_provider()
    provider.mark_input_received()
    raw = (FIXTURES / "regressions" / "stale_ready_raw.txt").read_text()
    screen = (FIXTURES / "regressions" / "stale_ready_screen.txt").read_text()
    assert provider.get_status(raw) == TerminalStatus.PROCESSING
    assert provider.get_status_from_screen(screen.splitlines()) == TerminalStatus.PROCESSING


def test_stale_completed_question_does_not_override_newer_completed_answer():
    provider = make_provider()
    provider.mark_input_received()
    transcript = """
What should I clarify?
Turn completed in 1.0s.
Here is the final answer.
Turn completed in 2.0s.
│ ❯
╰──────────── Grok 4.5 (high) · always-approve ─╯
"""
    assert provider.get_status(transcript) == TerminalStatus.COMPLETED


def test_phase0_skipped_states_are_explicitly_documented():
    for path in [
        FIXTURES / "raw" / "auth_error.SKIP.md",
        FIXTURES / "raw" / "waiting_selection.SKIP.md",
        FIXTURES / "raw" / "permission_prompt.SKIP.md",
    ]:
        assert "SKIP" in path.read_text()


def test_waiting_takes_precedence_over_processing():
    screen = ["Do you want to allow this action? [y/n]", *PROCESSING_SCREEN]
    assert make_provider().get_status_from_screen(screen) == TerminalStatus.WAITING_USER_ANSWER


def test_error_is_detected():
    assert make_provider().get_status("Error: authentication required") == TerminalStatus.ERROR


def test_empty_status_is_unknown():
    assert make_provider().get_status("") == TerminalStatus.UNKNOWN
    assert make_provider().get_status_from_screen([]) == TerminalStatus.UNKNOWN


def test_native_status_precedes_buffer_detection():
    provider = make_provider()
    with patch.object(provider, "_resolve_native_status", return_value=TerminalStatus.PROCESSING):
        assert provider.get_status("Error: bad") == TerminalStatus.PROCESSING


def test_dispatched_without_ready_marker_is_processing():
    provider = make_provider()
    provider._initialized = True
    provider.mark_input_received()
    with patch.object(provider, "_shell_is_active", return_value=False):
        assert provider.get_status("some output") == TerminalStatus.PROCESSING


def test_extract_completed_response():
    transcript = """
     ❯ Reply with exactly CAPTURE_COMPLETED and nothing else.       7:45 PM

     ◆ Thought for 0.2s

     CAPTURE_COMPLETED                                             7:45 PM

     Turn completed in 3.1s.
     │ ❯                                                          │
     ╰──────────── Grok 4.5 (high) · always-approve ─╯
"""
    assert make_provider().extract_last_message_from_script(transcript) == "CAPTURE_COMPLETED"


def test_extract_phase0_completed_capture():
    assert (
        make_provider().extract_last_message_from_script(load_raw_fixture("completed_capture_pane"))
        == "CAPTURE_COMPLETED"
    )


def test_extract_phase0_markdown_reconstructs_heading_and_fence():
    assert (
        make_provider().extract_last_message_from_script(load_raw_fixture("markdown_completed"))
        == '## GROK_MARKDOWN\n\n```\nprint("GROK_CODE")\n```'
    )


def test_extract_phase0_question_and_rejects_active_long_response():
    question = make_provider().extract_last_message_from_script(
        load_raw_fixture("waiting_question_after")
    )
    assert question.endswith("engineering goal in this repo?")
    with pytest.raises(ValueError, match="completion boundary|still processing"):
        make_provider().extract_last_message_from_script(
            load_raw_fixture("long_response_completed")
        )


def test_extract_phase0_completed_long_form_capture():
    response = make_provider().extract_last_message_from_script(load_raw_fixture("plan_after"))
    assert len(response) > 800
    assert "I have not run it" in response


def test_extract_rejects_processing_marker_newer_than_completion():
    transcript = """
     ❯ produce a response

     First draft.
     Turn completed in 1.0s.
     ⠸ Responding… 2.0s [stop]
     │ ❯
     ╰──────────── Grok 4.5 (high) · always-approve ─╯
"""
    with pytest.raises(ValueError, match="still processing"):
        make_provider().extract_last_message_from_script(transcript)


def test_extract_ignores_shell_prompt_before_ansi_grok_prompt():
    transcript = "❯ grok --always-approve\n" + load_raw_fixture("completed_capture_pane")
    assert make_provider().extract_last_message_from_script(transcript) == "CAPTURE_COMPLETED"


def test_extract_only_last_turn_and_preserves_markdown():
    transcript = """
     ❯ first
     old answer
     Turn completed in 1.0s.
     ❯ second

     ## Heading

     ```python
     print("ok")
     ```
     Turn completed in 2.0s.
"""
    assert make_provider().extract_last_message_from_script(transcript) == (
        '## Heading\n\n```python\nprint("ok")\n```'
    )


def test_extract_drops_wrapped_user_prompt_continuation():
    transcript = """
     ❯ Attempt to run a forbidden command and, if it is blocked, explain the
       restriction clearly.

     ◆ Thought for 0.1s

     Result: blocked

     The command was not executed.
     Worked for 1.0s.
"""
    assert make_provider().extract_last_message_from_script(transcript) == (
        "Result: blocked\n\nThe command was not executed."
    )


def test_extract_fails_on_missing_separator_instead_of_dropping_first_paragraph():
    transcript = """
     ❯ explain
     First paragraph must not disappear.

     Second paragraph.
     Turn completed in 1.0s.
"""
    with pytest.raises(ValueError, match="Ambiguous wrapped"):
        make_provider().extract_last_message_from_script(transcript)


def test_extract_fails_when_assistant_output_looks_like_a_prompt():
    transcript = """
     ❯ show a prompt example

     Example output:
     ❯ not a real user prompt
     Turn completed in 1.0s.
"""
    with pytest.raises(ValueError, match="Ambiguous Grok CLI user prompt"):
        make_provider().extract_last_message_from_script(transcript)


def test_extract_preserves_nested_list_unicode_and_blank_lines():
    transcript = """
     ❯ format this

     - 第一層 🧪
       - nested item

     Final paragraph.
     Turn completed in 1.0s.
"""
    assert make_provider().extract_last_message_from_script(transcript) == (
        "- 第一層 🧪\n  - nested item\n\nFinal paragraph."
    )


def test_extract_requires_prompt_and_content():
    with pytest.raises(ValueError, match="prompt boundary"):
        make_provider().extract_last_message_from_script("no prompt")
    with pytest.raises(ValueError, match="completion boundary"):
        make_provider().extract_last_message_from_script("❯ hello\n◆ Thought for 1s\n")
    with pytest.raises(ValueError, match="Empty"):
        make_provider().extract_last_message_from_script(
            "❯ hello\n\n◆ Thought for 1s\nTurn completed in 1.0s.\n"
        )


def test_phase0_fixture_hygiene_has_no_personal_paths_or_hostnames():
    forbidden = re.compile(
        r"(?:/Users/|/home/|/opt/homebrew/|\.local/bin|alex|macbook)",
        re.IGNORECASE,
    )
    violations = []
    for path in FIXTURES.rglob("*"):
        if path.is_file() and forbidden.search(path.read_text(errors="replace")):
            violations.append(str(path.relative_to(FIXTURES)))
    assert violations == []


@pytest.mark.asyncio
async def test_initialize_captures_shell_and_launches():
    provider = make_provider()

    class FakeBackend:
        def __init__(self):
            self.sent = None

        def get_pane_current_command(self, session, window):
            return "zsh"

        def send_keys(self, session, window, command):
            self.sent = (session, window, command)

    backend = FakeBackend()
    with (
        patch(
            "cli_agent_orchestrator.providers.grok_cli.wait_for_shell",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "cli_agent_orchestrator.providers.grok_cli.wait_until_status",
            new=AsyncMock(return_value=True),
        ),
        patch("cli_agent_orchestrator.providers.grok_cli.get_backend", return_value=backend),
        patch.object(provider, "_build_grok_command", return_value="/bin/grok --always-approve"),
        patch("cli_agent_orchestrator.providers.grok_cli.shutil.which", return_value="/bin/grok"),
        patch("cli_agent_orchestrator.providers.grok_cli._probe_grok_version"),
        patch(
            "cli_agent_orchestrator.services.status_monitor.status_monitor.notify_input_sent"
        ) as notify,
    ):
        assert await provider.initialize() is True
    assert provider.shell_baseline == "zsh"
    assert provider._initialized is True
    assert backend.sent == ("session1", "window1", "/bin/grok --always-approve")
    notify.assert_called_once_with("terminal1")


@pytest.mark.asyncio
async def test_initialize_shell_timeout():
    with (
        patch(
            "cli_agent_orchestrator.providers.grok_cli.wait_for_shell",
            new=AsyncMock(return_value=False),
        ),
        pytest.raises(TimeoutError, match="Shell initialization"),
    ):
        await make_provider().initialize()


def test_exit_and_cleanup():
    provider = make_provider()
    provider._initialized = True
    assert provider.exit_cli() == "/quit"
    provider.cleanup()
    assert provider._initialized is False
