import sqlite3

from cli_agent_orchestrator.clients.database import (
    _migrate_worker_token_usage,
    record_worker_token_usage,
)
from cli_agent_orchestrator.models.token_usage import TokenUsage


def _seed_usage(db_file, rows):
    with sqlite3.connect(str(db_file)) as conn:
        conn.executemany(
            "INSERT INTO worker_token_usage ("
            "id, terminal_id, provider, agent, run_id, step_id, model, effort, progress, "
            "input_tokens, output_tokens, total_tokens, estimated, recorded_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


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


def test_token_usage_page_keyset_and_summary_share_filters(client, tmp_path, monkeypatch):
    db_file = tmp_path / "usage-page.db"
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_file)
    _migrate_worker_token_usage()
    _seed_usage(
        db_file,
        [
            ("a", "term-a", "codex", "planner", "run-1", "step-a", None, None, None, 10, 5, 15, 1, "2026-07-13T01:00:00+00:00"),
            ("b", "term-b", "codex", "reviewer", "run-1", "step-b", "gpt-5", "high", None, 20, 10, 30, 1, "2026-07-13T02:00:00+00:00"),
            ("c", "term-c", "claude_code", "reviewer", "run-1", "step-c", "opus", "high", None, 30, 15, 45, 0, "2026-07-13T03:00:00+00:00"),
        ],
    )

    first = client.get("/token-usage/page", params={"provider": "codex", "limit": 1})
    assert first.status_code == 200
    first_body = first.json()
    assert [row["id"] for row in first_body["records"]] == ["b"]
    assert first_body["has_more"] is True
    assert first_body["snapshot_at"]

    second = client.get(
        "/token-usage/page",
        params={"provider": "codex", "limit": 1, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    assert [row["id"] for row in second.json()["records"]] == ["a"]
    assert second.json()["has_more"] is False

    summary = client.get("/token-usage/summary", params={"provider": "codex"})
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["attempts"] == 2
    assert summary_body["total_tokens"] == 45
    assert {group["value"] for group in summary_body["by_agent"]} == {"planner", "reviewer"}
    assert summary_body["by_model"] == [
        {"value": "gpt-5", "attempts": 1, "input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
        {"value": None, "attempts": 1, "input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    ]


def test_token_usage_page_same_timestamp_has_no_duplicates(client, tmp_path, monkeypatch):
    db_file = tmp_path / "usage-tie.db"
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_file)
    _migrate_worker_token_usage()
    timestamp = "2026-07-13T04:00:00+00:00"
    _seed_usage(
        db_file,
        [(record_id, "term", "codex", "agent", None, None, None, None, None, 1, 1, 2, 1, timestamp) for record_id in ("a", "b", "c")],
    )

    first = client.get("/token-usage/page", params={"limit": 2})
    second = client.get("/token-usage/page", params={"limit": 2, "cursor": first.json()["next_cursor"]})
    assert first.status_code == second.status_code == 200
    assert [row["id"] for row in first.json()["records"]] == ["c", "b"]
    assert [row["id"] for row in second.json()["records"]] == ["a"]
    assert len({row["id"] for row in first.json()["records"] + second.json()["records"]}) == 3


def test_token_usage_page_rejects_invalid_filters_and_cursor(client, tmp_path, monkeypatch):
    db_file = tmp_path / "usage-validation.db"
    monkeypatch.setattr("cli_agent_orchestrator.constants.DATABASE_FILE", db_file)
    _migrate_worker_token_usage()

    assert client.get("/token-usage/page", params={"provider": ""}).status_code == 422
    assert client.get("/token-usage/page", params={"provider": "__default__"}).status_code == 422
    assert client.get("/token-usage/page", params={"cursor": "not-a-cursor"}).status_code == 422
    assert client.get("/token-usage/page", params={"cursor": "!!!!"}).status_code == 422
