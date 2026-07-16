export interface WorkerTokenUsageRecord {
  id: string
  terminal_id: string
  provider: string
  agent: string
  run_id: string | null
  step_id: string | null
  model: string | null
  effort: string | null
  progress: string | null
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated: boolean
  recorded_at: string
}

export interface TokenUsageBucket {
  value: string | null
  attempts: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
}

export interface WorkerTokenUsagePage {
  records: WorkerTokenUsageRecord[]
  next_cursor: string | null
  has_more: boolean
  snapshot_at: string
}

export interface WorkerTokenUsageSummary {
  attempts: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  daily: TokenUsageBucket[]
  by_provider: TokenUsageBucket[]
  by_agent: TokenUsageBucket[]
  by_model: TokenUsageBucket[]
  by_effort: TokenUsageBucket[]
  snapshot_at: string
}
