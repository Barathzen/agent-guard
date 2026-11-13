import { useEffect, useMemo, useState } from 'react';
import {
  dashboardIdentity,
  fetchAgents,
  fetchAccounts,
  fetchUsage,
  sendGatewayRequest,
  setAgentPaused,
  streamBudgetUpdates,
} from './api';
import { Agent, SpendSummary, UsageRecord } from './types';
import './styles.css';

type IconName = 'grid' | 'activity' | 'shield' | 'settings' | 'refresh' | 'send' | 'pause' | 'play';

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, string> = {
    grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
    activity: 'M3 12h4l2-7 4 14 2-7h6',
    shield: 'M12 3 19 6v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3Z',
    settings: 'M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm0-5v2m0 13v2M4.6 7l1.7 1m11.4 6 1.7 1M4.6 17l1.7-1m11.4-6 1.7-1M7 12H3m18 0h-4',
    refresh: 'M20 11a8 8 0 0 0-14.9-3M4 5v4h4M4 13a8 8 0 0 0 14.9 3M20 19v-4h-4',
    send: 'm21 3-7.5 18-3.8-7.7L2 9.5 21 3Z',
    pause: 'M8 5v14M16 5v14',
    play: 'm8 5 11 7-11 7V5Z',
  };
  return <span className="icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg></span>;
}

const money = (value: string | number) => `$${Number(value).toFixed(4)}`;
const shortTime = (value: string) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

export default function App() {
  const [accounts, setAccounts] = useState<SpendSummary[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [usage, setUsage] = useState<UsageRecord[]>([]);
  const [paused, setPaused] = useState(true);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = async () => {
    try {
      setLoading(true);
      setError('');
      const [nextAccounts, nextUsage, nextAgents] = await Promise.all([
        fetchAccounts(), fetchUsage(), fetchAgents(),
      ]);
      setAccounts(nextAccounts);
      setUsage(nextUsage);
      setAgents(nextAgents);
      setLastUpdated(new Date());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Monitoring request failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    const controller = new AbortController();
    void streamBudgetUpdates(controller.signal, () => void refresh()).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Live stream failed');
    });
    return () => controller.abort();
  }, []);

  const totals = useMemo(() => accounts.reduce((result, account) => ({
    limit: result.limit + Number(account.budget_limit),
    settled: result.settled + Number(account.settled_spend),
    reserved: result.reserved + Number(account.reserved_amount),
  }), { limit: 0, settled: 0, reserved: 0 }), [accounts]);
  const filteredUsage = usage.filter((record) =>
    [record.request_id, record.agent_id, record.model_name].some((value) =>
      value.toLowerCase().includes(filter.toLowerCase())));
  const latest = usage[0];

  const dispatchRequest = async () => {
    try {
      setActionLoading(true);
      setMessage('');
      setError('');
      const response = await sendGatewayRequest({
        request_id: `req_${Date.now()}`, team_id: dashboardIdentity.teamId,
        agent_id: dashboardIdentity.agentId, session_id: dashboardIdentity.sessionId,
        model: 'mock-gpt-4o', messages: [{ role: 'user', content: 'Execute task iteration' }],
        max_output_tokens: 150,
      });
      setMessage(`${response.model} settled ${money(response.actual_cost)}${response.substitution_reason ? ` · ${response.substitution_reason}` : ''}`);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Gateway request failed');
    } finally {
      setActionLoading(false);
    }
  };

  const toggleAgent = async () => {
    try {
      setActionLoading(true);
      await setAgentPaused(dashboardIdentity.agentId, !paused);
      setPaused(!paused);
      setMessage(`Agent ${!paused ? 'paused' : 'resumed'} successfully`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Agent status update failed');
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">A</div><div><strong>AGENTGUARD</strong><small>CONTROL PLANE</small></div></div>
        <div className="nav-label">WORKSPACE</div>
        <nav className="nav" aria-label="Primary navigation">
          <button className="active"><Icon name="grid" />Overview</button>
          <button><Icon name="activity" />Usage ledger</button>
          <button><Icon name="shield" />Guardrails</button>
          <button><Icon name="settings" />Configuration</button>
        </nav>
        <div className="sidebar-footer">
          <div className="connection"><span className="dot" />Live connection</div>
          <div>PostgreSQL · local</div>
          <div style={{ marginTop: 5 }}>API v1 · authenticated</div>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div><p className="eyebrow">/ OVERVIEW</p><h1>Spend intelligence</h1><p className="subtitle">Live budget utilization, ledger activity, and runaway-agent controls.</p></div>
          <div className="top-actions">
            <span className="status-pill"><span className="dot" />STREAMING</span>
            <button className="ghost" onClick={() => void refresh()} disabled={loading} aria-label="Refresh dashboard"><Icon name="refresh" /> <span>Refresh</span></button>
            <button className={paused ? 'primary' : 'danger'} onClick={() => void toggleAgent()} disabled={actionLoading}>
              <Icon name={paused ? 'play' : 'pause'} /> {paused ? 'Resume agent' : 'Pause agent'}
            </button>
          </div>
        </header>

        {error && <div className="alert" role="alert"><span>{error}</span><button onClick={() => void refresh()}>Retry</button></div>}
        {message && <div className="alert" style={{ color: '#b8f5d6', background: '#0e2829', borderColor: '#205b4f' }} role="status">{message}</div>}

        <section className="kpis" aria-label="Summary metrics">
          <article className="card kpi"><div className="kpi-label">Committed spend <span>USD</span></div><div className="kpi-value">{money(totals.settled + totals.reserved)}</div><div className="kpi-meta">Across {accounts.length} budget scopes</div></article>
          <article className="card kpi"><div className="kpi-label">Available budget <span>01</span></div><div className="kpi-value">{money(Math.max(0, totals.limit - totals.settled - totals.reserved))}</div><div className="kpi-meta good">Within global limits</div></article>
          <article className="card kpi"><div className="kpi-label">Managed agents <span>LIVE</span></div><div className="kpi-value">{agents.length}</div><div className="kpi-meta">{agents.filter((agent) => agent.status === 'ACTIVE').length} active · {agents.filter((agent) => agent.status !== 'ACTIVE').length} paused</div></article>
          <article className="card kpi"><div className="kpi-label">Agent status <span>LIVE</span></div><div className="kpi-value" style={{ color: paused ? 'var(--amber)' : 'var(--green)' }}>{paused ? 'Paused' : 'Active'}</div><div className="kpi-meta mono">{dashboardIdentity.agentId}</div></article>
        </section>

        <div className="section-head"><h2>Budget health</h2><span>{lastUpdated ? `updated ${lastUpdated.toLocaleTimeString()}` : 'loading...'}</span></div>
        <section className="budget-grid" aria-label="Budget health">
          {accounts.map((account) => {
            const utilization = Math.min(100, Number(account.utilization_pct));
            const warning = utilization >= 80;
            return <article className="card budget" key={account.entity_id}>
              <div className="budget-heading"><div><div className="scope">{account.scope} SCOPE</div><h3>{account.entity_id}</h3></div><span className={`badge ${warning ? 'warn' : ''}`}>{warning ? 'ATTENTION' : 'HEALTHY'}</span></div>
              <div className="progress-track"><div className={`progress-bar ${warning ? 'warn' : ''}`} style={{ width: `${utilization}%` }} /></div>
              <div className="budget-stats"><span>Utilization <strong>{utilization.toFixed(1)}%</strong></span><span>Limit <strong>{money(account.budget_limit)}</strong></span></div>
              <div className="budget-stats" style={{ marginTop: 8 }}><span>Settled {money(account.settled_spend)}</span><span>Reserved {money(account.reserved_amount)}</span></div>
            </article>;
          })}
        </section>

        <div className="section-head"><h2>Operations</h2><span>CONTROL ACTIONS</span></div>
        <section className="lower-grid">
          <article className="card panel">
            <div className="panel-header"><h2>Recent usage</h2><input aria-label="Filter usage" placeholder="Filter requests..." value={filter} onChange={(event) => setFilter(event.target.value)} style={{ background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 6, color: 'var(--text)', padding: '7px 9px', fontSize: 11 }} /></div>
            <div className="table-wrap"><table><thead><tr><th>Request</th><th>Agent</th><th>Model</th><th>Tokens</th><th>Cost</th><th>Time</th></tr></thead><tbody>
              {filteredUsage.map((record) => <tr key={record.request_id}><td className="mono">{record.request_id}</td><td>{record.agent_id}</td><td><span className="badge">{record.model_name}</span></td><td className="mono dim">{record.actual_input_tokens + record.actual_output_tokens}</td><td className="mono">{money(record.actual_cost)}</td><td className="dim">{shortTime(record.created_at)}</td></tr>)}
              {!filteredUsage.length && <tr><td className="empty" colSpan={6}>No matching usage records.</td></tr>}
            </tbody></table></div>
          </article>
          <div style={{ display: 'grid', gap: 13, alignContent: 'start' }}>
            <article className="card panel"><div className="panel-header"><h2>Agent roster</h2><span>{agents.length} REGISTERED</span></div><div className="event-list">
              {agents.map((agent) => <div className="event" key={agent.id}><span className={`event-marker ${agent.status === 'ACTIVE' ? 'green' : ''}`} /><div style={{ minWidth: 0, flex: 1 }}><div className="event-title" style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}><span>{agent.name}</span><span className="badge">{agent.status}</span></div><div className="event-time">{agent.id} · team {agent.team_id}</div></div></div>)}
              {!agents.length && <div className="empty">No agents registered.</div>}
            </div></article>
            <article className="card panel"><div className="panel-header"><h2>Quick dispatch</h2><span>MOCK PROVIDER</span></div><div className="simulator"><p>Send a controlled request through the gateway to verify reservation, routing, and settlement.</p><div className="button-row"><button className="primary" onClick={() => void dispatchRequest()} disabled={actionLoading || paused}><Icon name="send" /> {actionLoading ? 'Working...' : 'Dispatch request'}</button>{paused && <span className="dim" style={{ alignSelf: 'center', fontSize: 11 }}>Resume agent first</span>}</div></div></article>
            <article className="card panel"><div className="panel-header"><h2>Activity</h2><span>LIVE FEED</span></div><div className="event-list"><div className="event"><span className="event-marker green" /><div><div className="event-title">Budget stream connected</div><div className="event-time">REAL-TIME · SSE</div></div></div>{latest && <div className="event"><span className="event-marker" /><div><div className="event-title">Request settled on {latest.model_name}</div><div className="event-time">{shortTime(latest.created_at)} · {money(latest.actual_cost)}</div></div></div>}<div className="event"><span className="event-marker" /><div><div className="event-title">Guardrail policy active</div><div className="event-time">20% runaway threshold</div></div></div></div></article>
          </div>
        </section>
      </main>
    </div>
  );
}
