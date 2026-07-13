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
