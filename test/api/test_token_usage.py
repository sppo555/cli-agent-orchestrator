from cli_agent_orchestrator.clients.database import (
    _migrate_worker_token_usage,
    record_worker_token_usage,
)
from cli_agent_orchestrator.models.token_usage import TokenUsage


def test_token_usage_endpoint_returns_persisted_worker_record(client, tmp_path, monkeypatch):
    db_file = tmp_path / "usage-api.db"
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_file)
    _migrate_worker_token_usage()
    record_worker_token_usage(
        terminal_id="abc12345",
        provider="claude_code",
        agent="reviewer",
        run_id="run-1",
        step_id="slice7",
        usage=TokenUsage(
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            model="claude-sonnet",
            effort="high",
            progress=".cao/worker-results/20260713T010600Z-v0.7.0-slice7-admin-reset-plan-review-r2-reviewer.md",
        ),
    )

    response = client.get("/token-usage", params={"terminal_id": "abc12345"})

    assert response.status_code == 200
    assert response.json()[0]["model"] == "claude-sonnet"
    assert response.json()[0]["effort"] == "high"
    assert response.json()[0]["progress"].endswith("r2-reviewer.md")
