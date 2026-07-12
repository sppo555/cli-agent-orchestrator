from cli_agent_orchestrator.services.token_usage import (
    add_token_usage,
    estimate_token_usage,
    estimate_tokens,
    resolve_worker_progress,
)


def test_estimate_tokens_uses_ceiling_four_chars_per_token():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_estimate_token_usage_separates_prompt_and_response():
    usage = estimate_token_usage(
        "12345678",
        "abcdefgh",
        model="claude-sonnet",
        effort="high",
        progress=".cao/worker-results/review.md",
    )
    assert usage.input_tokens == 2
    assert usage.output_tokens == 2
    assert usage.total_tokens == 4
    assert usage.estimated is True
    assert usage.model == "claude-sonnet"
    assert usage.effort == "high"
    assert usage.progress == ".cao/worker-results/review.md"


def test_add_token_usage_accumulates_retries():
    first = estimate_token_usage("1234", "abcd")
    second = estimate_token_usage("12345678", "abcdefgh")
    combined = add_token_usage(first, second)
    assert combined.input_tokens == 3
    assert combined.output_tokens == 3
    assert combined.total_tokens == 6


def test_resolve_worker_progress_prefers_explicit_then_artifact_path():
    artifact = (
        ".cao/worker-results/20260713T010600Z-v0.7.0-slice7-admin-reset-plan-review-r2-reviewer.md"
    )
    assert resolve_worker_progress("explicit.md", "", artifact) == "explicit.md"
    assert resolve_worker_progress(None, "wrote " + artifact, "") == artifact
