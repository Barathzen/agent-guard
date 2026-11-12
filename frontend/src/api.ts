import { ChatResponse, SpendSummary, UsageRecord } from './types';

const API_BASE = 'http://localhost:8000/api/v1';

export async function fetchAccounts(): Promise<SpendSummary[]> {
  const ids = ['team_alpha', 'agent_coder', 'session_init'];
  return Promise.all(ids.map(async (id, index) => {
    const scope = index === 0 ? 'TEAM' : index === 1 ? 'AGENT' : 'SESSION';
    const res = await fetch(`${API_BASE}/monitoring/summary/${scope}/${id}`);
    if (!res.ok) throw new Error(`Failed to fetch ${scope.toLowerCase()} budget`);
    const summary: SpendSummary = await res.json();
    return summary;
  }));
}

export async function fetchUsage(): Promise<UsageRecord[]> {
  const res = await fetch(`${API_BASE}/monitoring/usage?limit=25`);
  if (!res.ok) throw new Error('Failed to fetch usage history');
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
  const res = await fetch(`${API_BASE}/gateway/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-API-Key': 'dev-gateway-key' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export async function setAgentPaused(agentId: string, paused: boolean): Promise<void> {
  const res = await fetch(`${API_BASE}/agents/${agentId}/${paused ? 'pause' : 'resume'}`, {
    method: 'POST',
    headers: { 'X-API-Key': 'dev-gateway-key' },
  });
  if (!res.ok) throw new Error(`Failed to ${paused ? 'pause' : 'resume'} agent`);
}