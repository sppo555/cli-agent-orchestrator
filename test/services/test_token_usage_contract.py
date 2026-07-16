from dataclasses import replace
from pathlib import Path

import pytest

from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.models.token_usage import TokenUsage
from cli_agent_orchestrator.services.token_usage_contract import (
    PROVIDER_USAGE_INVENTORY,
    UsageSource,
    estimated_for_usage_source,
    extract_usage,
    usage_source_from_estimated,
    usage_source_from_record,
    validate_provider_usage_inventory,
)


def test_inventory_has_one_schema_complete_row_for_each_provider():
    assert {entry.provider for entry in PROVIDER_USAGE_INVENTORY} == {
        provider.value for provider in ProviderType
    }
    validate_provider_usage_inventory()
    assert {
        entry.provider for entry in PROVIDER_USAGE_INVENTORY if entry.machine_readable_usage
    } == {
        ProviderType.CLAUDE_CODE.value,
        ProviderType.CODEX.value,
        ProviderType.GROK_CLI.value,
    }
    document = (
        Path(__file__).parents[2] / "CAO-WORKER-TOKEN-USAGE-PROVIDER-INVENTORY.md"
    ).read_text()
    assert all(f"| `{provider.value}` |" in document for provider in ProviderType)
    assert "待确认" not in document


def test_inventory_validation_rejects_missing_evidence_field():
    incomplete = [replace(PROVIDER_USAGE_INVENTORY[0], fixture_provenance="")]
    incomplete.extend(PROVIDER_USAGE_INVENTORY[1:])

    with pytest.raises(ValueError, match="fixture provenance"):
        validate_provider_usage_inventory(incomplete)


def test_contract_does_not_parse_unknown_provider_or_response_text():
    assert extract_usage("unknown-provider", {}, "tokens: 123 input 456") is None
    assert extract_usage(ProviderType.CODEX.value, {}, "usage 999") is None


def test_legacy_boolean_mapping_is_conservative():
    assert usage_source_from_estimated(False) is UsageSource.NATIVE
    assert usage_source_from_estimated(True) is UsageSource.ESTIMATED
    assert estimated_for_usage_source(UsageSource.NATIVE) is False
    assert estimated_for_usage_source(UsageSource.ESTIMATED) is True
    assert estimated_for_usage_source(UsageSource.UNKNOWN) is True
    assert usage_source_from_record(TokenUsage(estimated=True)) is UsageSource.ESTIMATED
    assert usage_source_from_record(TokenUsage(estimated=False)) is UsageSource.NATIVE
