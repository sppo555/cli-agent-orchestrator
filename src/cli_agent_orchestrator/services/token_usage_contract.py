"""Provider token-usage inventory and the pre-adapter extraction contract.

This module intentionally contains no provider parser. The shared worker path
remains estimate-only until a provider has evidence approved for the native
adapter patch.
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
    """Validated result an evidence-approved adapter may return later."""

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
            "Structured JSON/JSONL turn usage event."
            if provider.value in _NATIVE_PROVIDERS
            else "No native usage source approved."
        ),
        field_semantics=(
            "Non-negative input_tokens/output_tokens; total is input plus output."
            if provider.value in _NATIVE_PROVIDERS
            else "Input/output/total/cache/reasoning semantics are unavailable."
        ),
        fixture_provenance=(
            "Sanitized contract fixture in test/services/fixtures; no prompt or transcript."
            if provider.value in _NATIVE_PROVIDERS
            else "No sanitized usage fixture; adapter not approved."
        ),
        fallback_behavior="Return None and keep the shared 4-chars-per-token estimate.",
        privacy_boundary="Do not add a parser that captures prompt, response, or transcript text.",
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
