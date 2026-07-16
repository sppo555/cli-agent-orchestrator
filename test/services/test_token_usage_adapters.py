from pathlib import Path

import pytest

from cli_agent_orchestrator.services.token_usage_adapters import (
    extract_claude_code_last_message,
    extract_claude_code_usage,
    extract_codex_last_message,
    extract_codex_usage,
    extract_grok_cli_last_message,
    extract_grok_cli_usage,
    extract_native_usage,
)
from cli_agent_orchestrator.services.token_usage_contract import UsageSource, extract_usage

FIXTURES = Path(__file__).parent / "fixtures"


def test_claude_fixture_extracts_final_native_usage():
    usage = extract_claude_code_usage((FIXTURES / "claude_code_usage_stream.jsonl").read_text())

    assert usage is not None
    assert usage.input_tokens == 120
    assert usage.output_tokens == 30
    assert usage.total_tokens == 150


def test_claude_native_usage_includes_cache_creation_and_read_input():
    raw = (
        '{"type":"result","usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":400,"cache_read_input_tokens":190000,'
        '"output_tokens":30}}'
    )

    usage = extract_claude_code_usage(raw)

    assert usage is not None
    assert usage.input_tokens == 190402
    assert usage.output_tokens == 30
    assert usage.total_tokens == 190432


def test_claude_structured_parser_extracts_result_message():
    raw = (
        '{"type":"assistant","message":{"content":[{"type":"text","text":"partial"}]}}\n'
        '{"type":"result","result":"final answer"}\n'
    )
    assert extract_claude_code_last_message(raw) == "final answer"


def test_codex_fixture_extracts_turn_usage_without_parsing_cached_subfield():
    usage = extract_codex_usage((FIXTURES / "codex_usage_stream.jsonl").read_text())

    assert usage is not None
    assert usage.input_tokens == 240
    assert usage.output_tokens == 40
    assert usage.total_tokens == 280


def test_codex_structured_parser_extracts_message_only_from_completed_items():
    raw = (
        '{"type":"item/agent_message/delta","delta":"first"}\n'
        '{"type":"item.completed","item":{"type":"agent_message","text":"final"}}\n'
    )
    assert extract_codex_last_message(raw) == "final"


def test_codex_structured_parser_can_reassemble_message_deltas():
    raw = (
        '{"type":"item/agent_message/delta","delta":"first"}\n'
        '{"type":"item/agent_message/delta","delta":" second"}\n'
    )
    assert extract_codex_last_message(raw) == "first second"


def test_provider_dispatch_and_contract_return_native_usage():
    raw = '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}'

    usage = extract_native_usage("codex", raw)
    contract_usage = extract_usage("codex", raw, "ordinary response")

    assert usage == contract_usage
    assert usage is not None
    assert UsageSource.NATIVE.value == "native"


def test_grok_fixture_extracts_cache_aware_native_usage_and_message():
    raw = (FIXTURES / "grok_cli_usage_stream.jsonl").read_text()

    usage = extract_grok_cli_usage(raw)

    assert usage is not None
    assert usage.input_tokens == 12772
    assert usage.output_tokens == 24
    assert usage.total_tokens == 12796
    assert usage.model == "grok-4.5"
    assert extract_grok_cli_last_message(raw) == "structured answer"
    assert extract_native_usage("grok_cli", raw) == usage


@pytest.mark.parametrize(
    "raw",
    [
        '{"type":"text","data":"usage: 10 tokens"}',
        '{"type":"end","usage":{"input_tokens":1,"output_tokens":2,"total_tokens":99}}',
        '{"type":"end","usage":{"input_tokens":1,"cache_read_input_tokens":-1,"output_tokens":2,"total_tokens":2}}',
        '{"type":"end","usage":{"input_tokens":1,"output_tokens":true,"total_tokens":2}}',
        "ordinary response with 12K / 500K",
    ],
)
def test_grok_malformed_or_tui_like_payload_falls_back(raw):
    assert extract_grok_cli_usage(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        '{"type":"turn.completed","usage":{"input_tokens":-1,"output_tokens":5}}',
        '{"type":"turn.completed","usage":{"input_tokens":1.5,"output_tokens":5}}',
        '{"type":"turn.completed","usage":{"input_tokens":"1","output_tokens":5}}',
        '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":5,"total_tokens":99}}',
        '{"type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":9,"output_tokens":3}}}}',
        "ordinary response with input_tokens=1 output_tokens=5",
        "{malformed json",
    ],
)
def test_malformed_or_false_positive_payload_falls_back(raw):
    assert extract_codex_usage(raw) is None
    assert extract_claude_code_usage(raw) is None
