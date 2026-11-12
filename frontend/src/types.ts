export interface BudgetAccount {
  id: string;
  budget_limit: string;
  settled_spend: string;
  reserved_amount: string;
  available: string;
  utilization_pct: string;
}

export interface ChatResponse {
  request_id: string;
  reservation_id: string;
  requested_model: string;
  content: string;
  model: string;
  actual_input_tokens: number;
  actual_output_tokens: number;
  actual_cost: string;
  substitution_reason?: string;
}

export interface UsageRecord {
  request_id: string;
  agent_id: string;
  session_id: string;
  model_name: string;
  actual_cost: string;
  actual_input_tokens: number;
  actual_output_tokens: number;
  created_at: string;
}

export interface SpendSummary extends BudgetAccount {
  entity_id: string;
  scope: string;
  rolling_60m_spend: string;
}