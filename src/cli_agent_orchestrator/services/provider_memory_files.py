"""Audit and scrub derivative provider-native CAO memory files."""

from pathlib import Path
from typing import Any

from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    BEGIN_MARKER as CLAUDE_BEGIN,
)
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import ClaudeCodeMemoryPlugin
from cli_agent_orchestrator.plugins.builtin.codex_memory import BEGIN_MARKER as CODEX_BEGIN
from cli_agent_orchestrator.plugins.builtin.codex_memory import CodexMemoryPlugin
from cli_agent_orchestrator.plugins.builtin.kiro_cli_memory import KiroCliMemoryPlugin


def _targets(project_dir: Path) -> list[tuple[str, Any, Path, str | None]]:
    base = project_dir.resolve(strict=True)
    plugins = [
        ("codex", CodexMemoryPlugin(), CODEX_BEGIN),
        ("claude_code", ClaudeCodeMemoryPlugin(), CLAUDE_BEGIN),
        ("kiro_cli", KiroCliMemoryPlugin(), None),
    ]
    return [
        (provider, plugin, plugin._validated_target_path(str(base)), marker)
        for provider, plugin, marker in plugins
    ]


def audit_provider_memory_files(project_dir: Path) -> list[dict[str, Any]]:
    """List CAO-managed derivative files without returning their content."""
    findings: list[dict[str, Any]] = []
    for provider, _plugin, target, marker in _targets(project_dir):
        if not target.exists():
            continue
        if marker is not None and marker not in target.read_text(encoding="utf-8"):
            continue
        findings.append(
            {
                "provider": provider,
                "path": str(target),
                "ownership": "managed-block" if marker is not None else "managed-file",
            }
        )
    return findings


def scrub_provider_memory_files(project_dir: Path, apply: bool = False) -> dict[str, Any]:
    """Plan or remove CAO-managed provider copies for a known project path."""
    findings = audit_provider_memory_files(project_dir)
    if apply:
        by_provider = {
            provider: (plugin, target) for provider, plugin, target, _ in _targets(project_dir)
        }
        for finding in findings:
            plugin, target = by_provider[finding["provider"]]
            if finding["ownership"] == "managed-file":
                target.unlink(missing_ok=True)
            else:
                plugin._write_block(target, "")
    return {
        "project_dir": str(project_dir.resolve(strict=True)),
        "applied": apply,
        "findings": findings,
    }
