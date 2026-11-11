import React, { useEffect, useState } from 'react';
import { fetchAccounts, createAccount, sendGatewayRequest } from './api';
import { BudgetAccount, ChatResponse } from './types';

export default function App() {
  const [accounts, setAccounts] = useState<BudgetAccount[]>([]);
  const [newId, setNewId] = useState('');
  const [newType, setNewType] = useState('AGENT');
  const [newLimit, setNewLimit] = useState('10.00');
  const [log, setLog] = useState<string[]>([]);

  const loadData = async () => {
    try {
      const data = await fetchAccounts();
      setAccounts(data);
    } catch (e: any) {
      appendLog(`Error: ${e.message}`);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const appendLog = (msg: string) => {
    setLog((prev) => [msg, ...prev]);
  };

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createAccount({ id: newId, account_type: newType, budget_limit: newLimit });
      setNewId('');
      appendLog(`Account created: ${newId}`);
      await loadData();
    } catch (e: any) {
      appendLog(`Account creation failed: ${e.message}`);
    }
  };

  const handleSimulateRequest = async () => {
    const reqId = `req_${Date.now()}`;
    try {
      appendLog(`Sending gateway request ${reqId}...`);
      const res: ChatResponse = await sendGatewayRequest({
        request_id: reqId,
        team_id: 'team_alpha',
        agent_id: 'agent_coder',
        session_id: 'session_init',
        model: 'mock-gpt-4o',
        messages: [{ role: 'user', content: 'Execute task iteration' }],
        max_output_tokens: 150,
      });
      appendLog(`Success: Settled $${res.actual_cost} for ${res.output_tokens} output tokens.`);
      await loadData();
    } catch (e: any) {
      appendLog(`Blocked/Failed: ${e.message}`);
    }
  };

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', padding: '2rem' }}>
      <h1>AgentGuard Governance Dashboard</h1>

      <div style={{ background: '#1e293b', padding: '1rem', borderRadius: '8px', marginBottom: '2rem' }}>
        <h3>Create Budget Account</h3>
        <form onSubmit={handleCreateAccount} style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <input
            placeholder="Account ID (e.g. team_alpha)"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            required
            style={{ padding: '0.5rem' }}
          />
          <select value={newType} onChange={(e) => setNewType(e.target.value)} style={{ padding: '0.5rem' }}>
            <option value="TEAM">TEAM</option>
            <option value="AGENT">AGENT</option>
            <option value="SESSION">SESSION</option>
          </select>
          <input
            placeholder="Limit (USD)"
            value={newLimit}
            onChange={(e) => setNewLimit(e.target.value)}
            required
            style={{ padding: '0.5rem' }}
          />
          <button type="submit" style={{ padding: '0.5rem 1rem', cursor: 'pointer' }}>Create</button>
        </form>
      </div>

      <div style={{ marginBottom: '2rem' }}>
        <button
          onClick={handleSimulateRequest}
          style={{ padding: '0.75rem 1.5rem', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
        >
          Dispatch Agent Request (Team: team_alpha | Agent: agent_coder | Session: session_init)
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        <div>
          <h3>Live Budget Accounts</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #475569' }}>
                <th>ID</th>
                <th>Type</th>
                <th>Limit</th>
                <th>Reserved</th>
                <th>Settled</th>
                <th>Available</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((acc) => (
                <tr key={acc.id} style={{ borderBottom: '1px solid #334155' }}>
                  <td>{acc.id}</td>
                  <td>{acc.account_type}</td>
                  <td>${parseFloat(acc.budget_limit).toFixed(4)}</td>
                  <td style={{ color: '#f59e0b' }}>${parseFloat(acc.reserved_amount).toFixed(4)}</td>
                  <td style={{ color: '#ef4444' }}>${parseFloat(acc.settled_spend).toFixed(4)}</td>
                  <td style={{ color: '#10b981' }}>${parseFloat(acc.available).toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <h3>Event Log</h3>
          <div style={{ background: '#020617', padding: '1rem', borderRadius: '4px', height: '260px', overflowY: 'auto' }}>
            {log.map((entry, idx) => (
              <div key={idx} style={{ fontSize: '0.85rem', marginBottom: '0.4rem', fontFamily: 'monospace' }}>
                &gt; {entry}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}