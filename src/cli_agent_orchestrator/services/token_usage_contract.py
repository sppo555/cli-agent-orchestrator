"""Provider token-usage inventory and the pre-adapter extraction contract.

This module intentionally contains no provider parser. The interactive worker
path remains estimate-only; the explicit structured worker dispatches only
providers with an evidence-approved native adapter.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.models.token_usage import TokenUsage


class UsageSource(str, Enum):
    """Provenance of a usage count, deliberately separate from billing."""

    NATIVE = "native"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class NativeUsage(BaseModel):
    """Validated result returned by an evidence-approved adapter."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    model: Optional[str] = None
    effort: Optional[str] = None


@dataclass(frozen=True)
class ProviderUsageInventory:
    """Evidence record required before a provider can enter native implementation."""

    provider: str
    machine_readable_usage: bool
    usage_source: str
    field_semantics: str
    fixture_provenance: str
    fallback_behavior: str
    privacy_boundary: str


_NATIVE_PROVIDERS = {ProviderType.CLAUDE_CODE.value, ProviderType.CODEX.value}

PROVIDER_USAGE_INVENTORY: tuple[ProviderUsageInventory, ...] = tuple(
    ProviderUsageInventory(
        provider=provider.value,
        machine_readable_usage=provider.value in _NATIVE_PROVIDERS,
        usage_source=(
            "Structured JSON plus deterministic interactive session JSONL."
            if provider is ProviderType.CLAUDE_CODE
            else (
                "Structured JSONL plus the rollout opened by the interactive Codex process."
                if provider is ProviderType.CODEX
                else "No native usage source approved."
            )
        ),
        field_semantics=(
            "Input includes uncached, cache-creation, and cache-read tokens; total adds output."
            if provider is ProviderType.CLAUDE_CODE
            else (
                "Provider input includes cached input; cumulative turn delta plus output."
                if provider is ProviderType.CODEX
                else "Input/output/total/cache/reasoning semantics are unavailable."
            )
        ),
        fixture_provenance=(
            "Sanitized structured fixture plus metadata-only interactive unit fixtures."
            if provider.value in _NATIVE_PROVIDERS
            else "No sanitized usage fixture; adapter not approved."
        ),
        fallback_behavior=(
            "Omit native interactive records when exact provider evidence is unavailable."
            if provider.value in _NATIVE_PROVIDERS
            else "Return None and keep the shared 4-chars-per-token estimate where supported."
        ),
        privacy_boundary=(
            "Read usage metadata only; never persist prompt, response, transcript, or source path."
        ),
    )
    for provider in ProviderType
)


def validate_provider_usage_inventory(
    inventory: Sequence[ProviderUsageInventory] = PROVIDER_USAGE_INVENTORY,
) -> None:
    """Validate the matrix before a provider can enter native implementation."""

    expected = {provider.value for provider in ProviderType}
    actual = {entry.provider for entry in inventory}
    if actual != expected or len(inventory) != len(expected):
        raise ValueError(f"provider inventory must contain exactly {sorted(expected)}")
    required = {
        "usage_source": "usage source",
        "field_semantics": "field semantics",
        "fixture_provenance": "fixture provenance",
        "fallback_behavior": "fallback behavior",
        "privacy_boundary": "privacy boundary",
    }
    for entry in inventory:
        for field, label in required.items():
            if not getattr(entry, field).strip():
                raise ValueError(f"{entry.provider} is missing {label}")


def extract_usage(
    provider: str,
    execution_context: Any,
    final_response: str,
) -> Optional[NativeUsage]:
    """Return native usage only when a later adapter has approved evidence.

    Only Claude Code and Codex have adapters in this patch. Keeping the seam
    strict lets every missing or malformed event fall back without changing
    worker completion or parsing ordinary response text.
    """

    del final_response
    from cli_agent_orchestrator.services.token_usage_adapters import extract_native_usage

    return extract_native_usage(provider, execution_context)


def usage_source_from_estimated(estimated: bool) -> UsageSource:
    """Map the legacy boolean to the conservative provenance contract."""

    return UsageSource.ESTIMATED if estimated else UsageSource.NATIVE


def estimated_for_usage_source(source: UsageSource) -> bool:
    """Keep legacy ``estimated`` true for both estimated and unknown values."""

    return source is not UsageSource.NATIVE


def usage_source_from_record(usage: TokenUsage) -> UsageSource:
    """Expose the compatibility mapping for an existing ``TokenUsage``."""

    return usage_source_from_estimated(usage.estimated)


validate_provider_usage_inventory()
