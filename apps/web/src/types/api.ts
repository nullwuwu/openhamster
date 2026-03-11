export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface RunMetricSnapshot {
  cagr: number | null
  max_drawdown: number | null
  sharpe: number | null
  annual_turnover: number | null
  data_years: number | null
  metadata_payload: Record<string, unknown>
  created_at: string
}

export interface BacktestRun {
  id: string
  symbol: string
  strategy_name: string
  provider_name: string
  status: RunStatus
  request_payload: Record<string, unknown>
  response_payload?: Record<string, unknown>
  error_message?: string
  created_at: string
  started_at?: string
  finished_at?: string
  updated_at: string
  metrics: RunMetricSnapshot[]
}

export interface ExperimentRun {
  id: string
  kind: 'optimizer' | 'walkforward'
  symbol: string
  strategy_name: string
  provider_name: string
  status: RunStatus
  request_payload: Record<string, unknown>
  response_payload?: Record<string, unknown>
  error_message?: string
  created_at: string
  started_at?: string
  finished_at?: string
  updated_at: string
  metrics: RunMetricSnapshot[]
}

export interface StrategySnapshot {
  strategy_name: string
  description: string
  enabled: boolean
  default_params: Record<string, unknown>
  updated_at: string
}

export interface Overview {
  generated_at: string
  timezone: string
  total_backtest_runs: number
  total_experiment_runs: number
  running_jobs: number
  latest_backtest: BacktestRun | null
  latest_experiment: ExperimentRun | null
  latest_total_equity: number | null
  latest_trade_date: string | null
}

export interface PaperNavPoint {
  trade_date: string
  cash: number
  position_value: number
  total_equity: number
}

export interface PaperOrder {
  id: number
  symbol: string
  side: string
  quantity: number
  price: number
  amount: number
  status: string
  created_at: string
}

export interface PaperPosition {
  id: number
  symbol: string
  quantity: number
  avg_cost: number
  market_value: number
  updated_at: string
}
