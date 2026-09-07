"""Token usage value objects returned and persisted for worker steps."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    """Token usage for one completed worker step."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated: bool = True
    model: Optional[str] = None
    effort: Optional[str] = None
    progress: Optional[str] = None


class WorkerTokenUsageRecord(TokenUsage):
    """Durable usage record for one completed worker attempt."""

    id: str
    terminal_id: str
    provider: str
    agent: str
    run_id: Optional[str] = None
    step_id: Optional[str] = None
    recorded_at: str
