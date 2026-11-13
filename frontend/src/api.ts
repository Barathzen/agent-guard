import { Agent, ChatResponse, SpendSummary, UsageRecord } from './types';

const API_BASE = 'http://localhost:8000/api/v1';
const API_KEY = import.meta.env.VITE_GATEWAY_API_KEY ?? 'dev-gateway-key';
const authHeaders = { 'X-API-Key': API_KEY };

export const dashboardIdentity = {
  teamId: import.meta.env.VITE_TEAM_ID ?? 'team_core',
  agentId: import.meta.env.VITE_AGENT_ID ?? 'agent_coder',
  sessionId: import.meta.env.VITE_SESSION_ID ?? 'session_init_01',
};

export async function streamBudgetUpdates(
  signal: AbortSignal,
  onBudgetEvent: () => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/monitoring/stream`, {
    headers: authHeaders,
    signal,
  });
  if (!res.ok) throw new Error(`Budget stream failed (${res.status})`);
  if (!res.body) throw new Error('Budget stream returned no body');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() ?? '';
    for (const event of events) {
      if (event.includes('event: budget')) onBudgetEvent();
    }
  }
}

export async function fetchAccounts(): Promise<SpendSummary[]> {
  const ids = [dashboardIdentity.teamId, dashboardIdentity.agentId, dashboardIdentity.sessionId];
  return Promise.all(ids.map(async (id, index) => {
    const scope = index === 0 ? 'TEAM' : index === 1 ? 'AGENT' : 'SESSION';
    const res = await fetch(`${API_BASE}/monitoring/summary/${scope}/${id}`, { headers: authHeaders });
    if (!res.ok) throw new Error(`Failed to fetch ${scope.toLowerCase()} budget`);
    const summary: SpendSummary = await res.json();
    return summary;
  }));
}

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${API_BASE}/agents`, { headers: authHeaders });
  if (!res.ok) throw new Error('Failed to fetch agent roster');
  return res.json();
}

export async function fetchUsage(): Promise<UsageRecord[]> {
  const res = await fetch(`${API_BASE}/monitoring/usage?limit=25`, { headers: authHeaders });
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
    headers: { 'Content-Type': 'application/json', ...authHeaders },
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
    headers: authHeaders,
  });
  if (!res.ok) throw new Error(`Failed to ${paused ? 'pause' : 'resume'} agent`);
}