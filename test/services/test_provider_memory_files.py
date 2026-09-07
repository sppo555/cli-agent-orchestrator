"""Tests for explicit provider-native derivative audit and scrub."""

from pathlib import Path

from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    BEGIN_MARKER as CLAUDE_BEGIN,
)
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    END_MARKER as CLAUDE_END,
)
from cli_agent_orchestrator.plugins.builtin.codex_memory import BEGIN_MARKER as CODEX_BEGIN
from cli_agent_orchestrator.plugins.builtin.codex_memory import END_MARKER as CODEX_END
from cli_agent_orchestrator.services.provider_memory_files import scrub_provider_memory_files


def test_provider_file_scrub_is_dry_run_by_default_and_preserves_user_bytes(
    tmp_path: Path,
) -> None:
    codex = tmp_path / "AGENTS.md"
    claude = tmp_path / ".claude" / "CLAUDE.md"
    kiro = tmp_path / ".kiro" / "steering" / "cao-memory.md"
    claude.parent.mkdir(parents=True)
    kiro.parent.mkdir(parents=True)
    codex_prefix, codex_suffix = "codex-before\n", "\ncodex-after\n"
    claude_prefix, claude_suffix = "claude-before\n", "\nclaude-after\n"
    codex.write_text(
        codex_prefix + f"{CODEX_BEGIN}\nstale\n{CODEX_END}" + codex_suffix,
        encoding="utf-8",
    )
    claude.write_text(
        claude_prefix + f"{CLAUDE_BEGIN}\nstale\n{CLAUDE_END}" + claude_suffix,
        encoding="utf-8",
    )
    kiro.write_text("stale\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (codex, claude, kiro)}

    dry_run = scrub_provider_memory_files(tmp_path)

    assert dry_run["applied"] is False
    assert dry_run["blocked"] == 0
    assert {item["provider"] for item in dry_run["findings"]} == {
        "codex",
        "claude_code",
        "kiro_cli",
    }
    assert {path: path.read_bytes() for path in (codex, claude, kiro)} == before

    applied = scrub_provider_memory_files(tmp_path, apply=True)

    assert applied["applied"] is True
    assert codex.read_text(encoding="utf-8") == codex_prefix + codex_suffix
    assert claude.read_text(encoding="utf-8") == claude_prefix + claude_suffix
    assert not kiro.exists()


def test_provider_file_scrub_ignores_unmanaged_user_files(tmp_path: Path) -> None:
    codex = tmp_path / "AGENTS.md"
    claude = tmp_path / ".claude" / "CLAUDE.md"
    claude.parent.mkdir(parents=True)
    codex.write_bytes(b"codex user bytes  \n")
    claude.write_bytes(b"claude user bytes  \n")

    report = scrub_provider_memory_files(tmp_path, apply=True)

    assert report["findings"] == []
    assert codex.read_bytes() == b"codex user bytes  \n"
    assert claude.read_bytes() == b"claude user bytes  \n"


def test_provider_file_scrub_reports_malformed_block_without_mutating(
    tmp_path: Path,
) -> None:
    """Ambiguous ownership is visible but never auto-repaired, even with --apply."""

    target = tmp_path / "AGENTS.md"
    original = f"user-prefix\n{CODEX_BEGIN}\nprivate stale payload\n"
    target.write_text(original, encoding="utf-8")

    report = scrub_provider_memory_files(tmp_path, apply=True)

    assert report["blocked"] == 1
    assert report["findings"] == [
        {
            "provider": "codex",
            "path": str(target),
            "ownership": "managed-block",
            "status": "malformed",
        }
    ]
    assert target.read_text(encoding="utf-8") == original
