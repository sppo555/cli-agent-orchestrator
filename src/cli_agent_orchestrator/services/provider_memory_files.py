"""Audit and scrub derivative provider-native CAO memory files."""

from pathlib import Path
from typing import Any

from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    BEGIN_MARKER as CLAUDE_BEGIN,
)
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import (
    END_MARKER as CLAUDE_END,
)
from cli_agent_orchestrator.plugins.builtin.claude_code_memory import ClaudeCodeMemoryPlugin
from cli_agent_orchestrator.plugins.builtin.codex_memory import BEGIN_MARKER as CODEX_BEGIN
from cli_agent_orchestrator.plugins.builtin.codex_memory import END_MARKER as CODEX_END
from cli_agent_orchestrator.plugins.builtin.codex_memory import CodexMemoryPlugin
from cli_agent_orchestrator.plugins.builtin.kiro_cli_memory import KiroCliMemoryPlugin
from cli_agent_orchestrator.plugins.builtin.memory_markers import (
    MalformedMemoryMarkersError,
    strip_managed_blocks,
)

PROTECTED_PROVIDER_MEMORY_PLUGINS = {
    "codex": CodexMemoryPlugin,
    "claude_code": ClaudeCodeMemoryPlugin,
    "kiro_cli": KiroCliMemoryPlugin,
}


def prepare_provider_memory_file(provider: str, terminal_id: str, working_directory: str) -> bool:
    """Prepare a protected provider file independently of plugin discovery.

    Returns ``False`` for providers without a native CAO memory derivative.
    Preparation failures propagate and must abort provider construction.
    """

    plugin_class = PROTECTED_PROVIDER_MEMORY_PLUGINS.get(provider)
    if plugin_class is None:
        return False
    plugin_class().prepare(terminal_id, working_directory)
    return True


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
        marker_status = "valid"
        if marker is not None:
            end_marker = CODEX_END if provider == "codex" else CLAUDE_END
            content = target.read_text(encoding="utf-8")
            try:
                stripped = strip_managed_blocks(content, marker, end_marker)
            except MalformedMemoryMarkersError:
                marker_status = "malformed"
            else:
                if stripped == content:
                    continue
        findings.append(
            {
                "provider": provider,
                "path": str(target),
                "ownership": "managed-file" if marker is None else "managed-block",
                "status": marker_status,
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
            if finding["status"] == "malformed":
                continue
            if finding["ownership"] == "managed-file":
                target.unlink(missing_ok=True)
            else:
                plugin._write_block(target, "")
    return {
        "project_dir": str(project_dir.resolve(strict=True)),
        "applied": apply,
        "blocked": sum(finding["status"] == "malformed" for finding in findings),
        "findings": findings,
    }
