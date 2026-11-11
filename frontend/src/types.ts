export interface BudgetAccount {
  id: string;
  account_type: 'TEAM' | 'AGENT' | 'SESSION';
  budget_limit: string;
  settled_spend: string;
  reserved_amount: string;
  available: string;
}

export interface ChatResponse {
  request_id: string;
  content: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  actual_cost: string;
}