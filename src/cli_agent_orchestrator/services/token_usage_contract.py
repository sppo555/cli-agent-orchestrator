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


PROVIDER_USAGE_INVENTORY: tuple[ProviderUsageInventory, ...] = tuple(
    ProviderUsageInventory(
        provider=provider.value,
        machine_readable_usage=False,
        usage_source="No native usage source observed in the CAO provider/runtime path.",
        field_semantics="Input/output/total/cache/reasoning semantics are unavailable.",
        fixture_provenance="No sanitized usage fixture; no adapter evidence approved.",
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

    4.17.3 deliberately returns ``None`` for every provider. Keeping this
    stable seam lets 4.17.4 add adapters without changing worker completion or
    allowing accidental numeric parsing from ordinary response text.
    """

    del provider, execution_context, final_response
    return None


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
