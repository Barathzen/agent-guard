import { BudgetAccount, ChatResponse } from './types';

const API_BASE = 'http://localhost:8000/api/v1';

export async function fetchAccounts(): Promise<BudgetAccount[]> {
  const res = await fetch(`${API_BASE}/accounts`);
  if (!res.ok) throw new Error('Failed to fetch accounts');
  return res.json();
}

export async function createAccount(data: {
  id: string;
  account_type: string;
  budget_limit: string;
}): Promise<BudgetAccount> {
  const res = await fetch(`${API_BASE}/accounts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create account');
  return res.json();
}

export async function sendGatewayRequest(payload: {
  request_id: string;
  team_id: string;
  agent_id: string;
  session_id: string;
  model: string;
  messages: { role: string; content: string }[];
  max_output_tokens: number;
}): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/gateway/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}