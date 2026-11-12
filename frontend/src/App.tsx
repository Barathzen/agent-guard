import { useEffect, useState } from 'react';
import { fetchAccounts, fetchUsage, sendGatewayRequest, setAgentPaused } from './api';
import { SpendSummary, UsageRecord } from './types';

const agentId = 'agent_coder';

export default function App() {
  const [accounts, setAccounts] = useState<SpendSummary[]>([]);
  const [usage, setUsage] = useState<UsageRecord[]>([]);
  const [paused, setPaused] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const refresh = async () => {
    try {
      setError('');
      const [nextAccounts, nextUsage] = await Promise.all([fetchAccounts(), fetchUsage()]);
      setAccounts(nextAccounts);
      setUsage(nextUsage);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Monitoring request failed');
    }
  };

  useEffect(() => {
    void refresh();
    const source = new EventSource('http://localhost:8000/api/v1/monitoring/stream');
    source.addEventListener('budget', () => void refresh());
    source.onerror = () => source.close();
    return () => source.close();
  }, []);

  const dispatchRequest = async () => {
    try {
      setMessage('');
      const response = await sendGatewayRequest({
        request_id: `req_${Date.now()}`,
        team_id: 'team_alpha',
        agent_id: agentId,
        session_id: 'session_init',
        model: 'mock-gpt-4o',
        messages: [{ role: 'user', content: 'Execute task iteration' }],
        max_output_tokens: 150,
      });
      setMessage(
        `${response.model} settled $${response.actual_cost}` +
          (response.substitution_reason ? ` (${response.substitution_reason})` : ''),
      );
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Gateway request failed');
    }
  };

  const toggleAgent = async () => {
    try {
      await setAgentPaused(agentId, !paused);
      setPaused(!paused);
      setMessage(`Agent ${!paused ? 'paused' : 'resumed'}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Agent status update failed');
    }
  };

  return (
    <main style={{ maxWidth: 1100, margin: '0 auto', padding: '2rem', fontFamily: 'system-ui' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <p style={{ color: '#38bdf8', letterSpacing: 2 }}>AGENTGUARD / CONTROL PLANE</p>
          <h1>Spend intelligence</h1>
          <p>Live budget utilization, ledger activity, and runaway-agent controls.</p>
        </div>
        <button onClick={toggleAgent}>{paused ? 'Resume agent' : 'Pause agent'}</button>
      </header>
      {error && <p role="alert" style={{ color: '#f87171' }}>{error}</p>}
      {message && <p style={{ color: '#34d399' }}>{message}</p>}
      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {accounts.map((account) => (
          <article key={account.entity_id} style={{ border: '1px solid #334155', borderRadius: 12, padding: 16 }}>
            <strong>{account.scope}</strong>
            <h2>{account.entity_id}</h2>
            <p>Utilization: {Number(account.utilization_pct).toFixed(2)}%</p>
            <progress value={Number(account.utilization_pct)} max={100} />
            <p>Settled ${Number(account.settled_spend).toFixed(6)}</p>
            <p>Reserved ${Number(account.reserved_amount).toFixed(6)}</p>
            <p>Rolling hour ${Number(account.rolling_60m_spend).toFixed(6)}</p>
          </article>
        ))}
      </section>
      <button onClick={dispatchRequest} style={{ margin: '24px 0' }}>Dispatch monitored request</button>
      <section>
        <h2>Recent usage</h2>
        <table style={{ width: '100%', textAlign: 'left' }}>
          <thead><tr><th>Request</th><th>Agent</th><th>Model</th><th>Cost</th><th>When</th></tr></thead>
          <tbody>
            {usage.map((record) => (
              <tr key={record.request_id}>
                <td>{record.request_id}</td>
                <td>{record.agent_id}</td>
                <td>{record.model_name}</td>
                <td>${Number(record.actual_cost).toFixed(6)}</td>
                <td>{new Date(record.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
