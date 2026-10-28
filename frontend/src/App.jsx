import { useState, useEffect, useCallback, useRef } from "react";
import {
  LayoutDashboard, Activity, Zap, AlertTriangle,
  BarChart3, Settings, ChevronRight, RefreshCw,
  CheckCircle, XCircle, Clock, Shield, X,
  TrendingUp, Database, Server, Cpu, Wifi,
  AlertCircle, Info
} from "lucide-react";
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  PieChart, Pie, Cell, ResponsiveContainer,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine
} from "recharts";
import "./App.css";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

// ── API helpers ────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ── Risk/status helpers ────────────────────────────────────────
function riskBadge(risk) {
  const cls = { HIGH: "badge-high", MEDIUM: "badge-medium", LOW: "badge-low" }[risk] || "badge-neutral";
  return <span className={`badge ${cls}`}>{risk ?? "—"}</span>;
}

function statusBadge(status) {
  const cls = {
    OPEN: "badge-open", ACKNOWLEDGED: "badge-acknowledged",
    INVESTIGATING: "badge-investigating", RESOLVED: "badge-resolved",
    CLOSED: "badge-closed",
  }[status] || "badge-neutral";
  return <span className={`badge ${cls}`}>{status ?? "—"}</span>;
}

function fmt(n, decimals = 1) {
  return n == null ? "—" : Number(n).toFixed(decimals);
}

function relTime(ts) {
  if (!ts) return "—";
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 60000) return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.round(diff / 60000)}m ago`;
  return new Date(ts).toLocaleString();
}

// ── Shared components ─────────────────────────────────────────

function LoadingPlaceholder({ rows = 4 }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 48, borderRadius: 10 }} />
      ))}
    </div>
  );
}

function AlertBox({ type = "error", title, children }) {
  return (
    <div className={`alert alert-${type}`} role="alert">
      {title && <strong>{title}</strong>}
      {children}
    </div>
  );
}

function EmptyState({ icon = "📭", message = "No data available." }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <p>{message}</p>
    </div>
  );
}

// Tooltip for recharts with dark theme
const DarkTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "var(--bg-raised)", border: "1px solid var(--border-normal)",
      borderRadius: 8, padding: "10px 14px", fontSize: 12,
    }}>
      <p style={{ color: "var(--text-muted)", marginBottom: 6 }}>{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: <strong>{p.value}</strong>
        </p>
      ))}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════
// VIEW: OVERVIEW
// ═══════════════════════════════════════════════════════════════
function OverviewView({ telemetry, telemetryError, health }) {
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(null);

  const fetchSummary = useCallback(async () => {
    try {
      const data = await apiFetch("/analytics/summary");
      setSummary(data);
      setSummaryError(null);
    } catch (e) {
      setSummaryError(e.message);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  const statusColor = health?.status === "healthy" ? "var(--color-low)"
    : health?.status === "degraded" ? "var(--color-med)"
    : "var(--color-high)";

  return (
    <div>
      {/* Hero */}
      <div className="hero-banner">
        <div>
          <p className="hero-eyebrow">AEGIS INTELLIGENCE PLATFORM</p>
          <h1 className="hero-title">
            Anticipate incidents<br /><span>before they happen.</span>
          </h1>
          <p className="hero-desc">
            AI-powered infrastructure observability. Monitor telemetry, detect
            anomalies, and predict operational failures in real time.
          </p>
        </div>
        <div className="hero-symbol">✳</div>
      </div>

      {/* System status bar */}
      {health && (
        <div className="card flex-row gap-16 mb-16" style={{ marginBottom: 20 }}>
          <div className="flex-row gap-8">
            <div className="pulse-dot" style={{ background: statusColor }} />
            <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
              System {health.status === "healthy" ? "Operational" : health.status?.toUpperCase()}
            </span>
          </div>
          {health.components && Object.entries(health.components).map(([k, v]) => {
            if (typeof v !== "object") return (
              <span key={k} className="text-sm text-secondary">
                {k}: <span className="text-mono" style={{ color: "var(--text-accent)" }}>{String(v)}</span>
              </span>
            );
            return (
              <span key={k} className="flex-row gap-8 text-sm text-secondary">
                {v.ok
                  ? <CheckCircle size={13} color="var(--color-low)" />
                  : <XCircle size={13} color="var(--color-high)" />
                }
                {k}
              </span>
            );
          })}
        </div>
      )}

      {/* KPI stats */}
      {summaryLoading ? (
        <div className="stats-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="stat-card">
              <div className="skeleton skeleton-text" />
              <div className="skeleton skeleton-value" style={{ height: 32 }} />
            </div>
          ))}
        </div>
      ) : summaryError ? (
        <AlertBox type="error" title="Analytics unavailable">{summaryError}</AlertBox>
      ) : summary && (
        <div className="stats-grid">
          <div className="stat-card">
            <span className="stat-label">Total Predictions</span>
            <span className="stat-value">{summary.total_predictions?.toLocaleString()}</span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Incidents Detected</span>
            <span className="stat-value" style={{ color: "var(--color-high)" }}>
              {summary.total_incidents_detected?.toLocaleString()}
            </span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Active Open</span>
            <span className="stat-value">
              {summary.active_incident_counts?.by_status?.OPEN ?? 0}
            </span>
          </div>
          <div className="stat-card">
            <span className="stat-label">High Risk Open</span>
            <span className="stat-value" style={{ color: "var(--color-high)" }}>
              {summary.high_risk_open ?? 0}
            </span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Avg Probability</span>
            <span className="stat-value">
              {((summary.average_probability ?? 0) * 100).toFixed(1)}
              <span className="stat-unit">%</span>
            </span>
          </div>
          <div className="stat-card">
            <span className="stat-label">Telemetry Source</span>
            <span className="stat-value" style={{ fontSize: 16 }}>
              {telemetry?.source ?? "—"}
            </span>
          </div>
        </div>
      )}

      {/* Live telemetry */}
      <div className="section">
        <div className="section-header">
          <div>
            <h2 className="section-title">Live Telemetry</h2>
            <p className="section-subtitle">
              CPU & memory are real psutil measurements · other metrics are simulated
            </p>
          </div>
          <span className="tag">{telemetry ? "LIVE" : "CONNECTING"}</span>
        </div>

        {telemetryError && (
          <AlertBox type="error" title="Telemetry unavailable">{telemetryError}</AlertBox>
        )}

        {telemetry && (
          <div className="metrics-grid">
            {[
              { key: "cpu",            label: "CPU Usage",      unit: "%",     icon: <Cpu size={13} /> },
              { key: "memory",         label: "Memory Usage",   unit: "%",     icon: <Server size={13} /> },
              { key: "request_rate",   label: "Request Rate",   unit: "req/s", icon: <Wifi size={13} /> },
              { key: "latency",        label: "Latency",        unit: "ms",    icon: <Activity size={13} /> },
              { key: "error_rate",     label: "Error Rate",     unit: "%",     icon: <AlertCircle size={13} /> },
              { key: "db_connections", label: "DB Connections", unit: "",      icon: <Database size={13} /> },
            ].map(({ key, label, unit, icon }) => (
              <div className="metric-tile" key={key}>
                <div className="metric-tile-label">
                  <span>{label}</span>
                  <span style={{ color: "var(--text-muted)" }}>{icon}</span>
                </div>
                <div className="metric-tile-value">
                  {fmt(telemetry[key])}
                  {unit && <span className="metric-tile-unit">{unit}</span>}
                </div>
              </div>
            ))}
          </div>
        )}

        {telemetry?.timestamp && (
          <p className="text-sm text-muted mt-12">
            Last updated: {new Date(telemetry.timestamp).toLocaleTimeString()}
            {telemetry.source && (
              <span className="source-label" style={{ marginLeft: 12 }}>
                <Info size={11} /> {telemetry.source}
              </span>
            )}
          </p>
        )}
      </div>

      {/* Recent incidents */}
      {summary?.recent_incidents?.length > 0 && (
        <div className="section">
          <div className="section-header">
            <h2 className="section-title">Recent Active Incidents</h2>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Risk</th>
                  <th>Status</th>
                  <th>Occurrences</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {summary.recent_incidents.map((inc) => (
                  <tr key={inc.id}>
                    <td><span className="text-mono">#{inc.id}</span></td>
                    <td>{riskBadge(inc.risk_level)}</td>
                    <td>{statusBadge(inc.status)}</td>
                    <td><strong>{inc.occurrence_count}</strong></td>
                    <td>{relTime(inc.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// VIEW: MONITORING (Infrastructure)
// ═══════════════════════════════════════════════════════════════
function MonitoringView({ telemetry, telemetryError, onSaveSnapshot }) {
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState(null);

  const fetchHistory = useCallback(async () => {
    try {
      const data = await apiFetch("/telemetry/history?limit=60");
      setHistory(data.history || []);
      setHistoryError(null);
    } catch (e) {
      setHistoryError(e.message);
    }
  }, []);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const chartData = history.map((h) => ({
    time: new Date(h.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    cpu: h.cpu,
    memory: h.memory,
    latency: h.latency,
    error_rate: h.error_rate,
    request_rate: h.request_rate,
  }));

  return (
    <div>
      <div className="page-topbar">
        <div>
          <h2 className="section-title">Infrastructure Monitoring</h2>
          <p className="section-subtitle">Real-time system telemetry and trend analysis</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={onSaveSnapshot}>
          <RefreshCw size={13} /> Save Snapshot
        </button>
      </div>

      {telemetryError && (
        <AlertBox type="error" title="Telemetry unavailable">{telemetryError}</AlertBox>
      )}

      {telemetry && (
        <div className="metrics-grid" style={{ marginBottom: 28 }}>
          {[
            { key: "cpu",            label: "CPU",          unit: "%",     warn: 80,  crit: 96 },
            { key: "memory",         label: "Memory",       unit: "%",     warn: 85,  crit: 97 },
            { key: "request_rate",   label: "Request Rate", unit: "req/s", warn: 200, crit: 300 },
            { key: "latency",        label: "Latency",      unit: "ms",    warn: 180, crit: 270 },
            { key: "error_rate",     label: "Error Rate",   unit: "%",     warn: 3.0, crit: 5.0 },
            { key: "db_connections", label: "DB Conns",     unit: "",      warn: 50,  crit: 80 },
          ].map(({ key, label, unit, warn, crit }) => {
            const val = telemetry[key];
            const numVal = Number(val);
            const isCrit = numVal >= crit;
            const isWarn = numVal >= warn;
            const cls = isCrit ? "anomaly-high" : isWarn ? "anomaly-medium" : "";
            return (
              <div className={`metric-tile ${cls}`} key={key}>
                <div className="metric-tile-label">
                  <span>{label}</span>
                  {isCrit && <span className="badge badge-high" style={{ fontSize: 9 }}>CRITICAL</span>}
                  {!isCrit && isWarn && <span className="badge badge-medium" style={{ fontSize: 9 }}>WARN</span>}
                </div>
                <div className="metric-tile-value">
                  {fmt(val)}
                  {unit && <span className="metric-tile-unit">{unit}</span>}
                </div>
                <div className="prob-bar-track" style={{ marginTop: 12 }}>
                  <div
                    className={`prob-bar-fill ${isCrit ? "high" : isWarn ? "medium" : "low"}`}
                    style={{ width: `${Math.min(100, (numVal / crit) * 100)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* CPU & Memory chart */}
      {chartData.length > 0 ? (
        <>
          <div className="two-col">
            <div className="card">
              <div className="card-header">
                <div>
                  <p className="card-title">CPU & Memory</p>
                  <p className="card-subtitle">Utilisation over time (%)</p>
                </div>
              </div>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="cpu-grad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#7b8fff" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#7b8fff" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="mem-grad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#a78bfa" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                    <XAxis dataKey="time" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                    <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} domain={[0, 100]} />
                    <Tooltip content={<DarkTooltip />} />
                    <ReferenceLine y={80} stroke="rgba(251,146,60,0.4)" strokeDasharray="4 3" />
                    <Area type="monotone" dataKey="cpu" stroke="#7b8fff" fill="url(#cpu-grad)" name="CPU %" strokeWidth={2} dot={false} />
                    <Area type="monotone" dataKey="memory" stroke="#a78bfa" fill="url(#mem-grad)" name="Memory %" strokeWidth={2} dot={false} />
                    <Legend wrapperStyle={{ fontSize: 11, color: "var(--text-secondary)" }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <div>
                  <p className="card-title">Latency & Error Rate</p>
                  <p className="card-subtitle">Response quality over time</p>
                </div>
              </div>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                    <XAxis dataKey="time" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                    <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                    <Tooltip content={<DarkTooltip />} />
                    <ReferenceLine y={180} stroke="rgba(251,146,60,0.4)" strokeDasharray="4 3" />
                    <Line type="monotone" dataKey="latency" stroke="#60a5fa" name="Latency ms" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="error_rate" stroke="#f87171" name="Error Rate %" strokeWidth={2} dot={false} />
                    <Legend wrapperStyle={{ fontSize: 11, color: "var(--text-secondary)" }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <p className="text-sm text-muted mt-12">
            {chartData.length} snapshots displayed · Click "Save Snapshot" to add the current reading to history
          </p>
        </>
      ) : (
        <div className="card mt-16">
          {historyError ? (
            <AlertBox type="error" title="History unavailable">{historyError}</AlertBox>
          ) : (
            <EmptyState
              icon="📈"
              message="No telemetry history yet. Click 'Save Snapshot' to start recording trend data."
            />
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// VIEW: PREDICTION
// ═══════════════════════════════════════════════════════════════
function PredictionView({ modelInfo }) {
  const [metrics, setMetrics] = useState({
    cpu: 30, memory: 40, request_rate: 100,
    latency: 80, error_rate: 0.5, db_connections: 20,
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const PRESETS = {
    Normal:    { cpu: 25,   memory: 38, request_rate: 95,  latency: 70,  error_rate: 0.3, db_connections: 15 },
    Warning:   { cpu: 72,   memory: 78, request_rate: 170, latency: 150, error_rate: 2.1, db_connections: 42 },
    "High Risk": { cpu: 92, memory: 91, request_rate: 270, latency: 225, error_rate: 4.5, db_connections: 72 },
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setMetrics((prev) => ({ ...prev, [name]: value }));
  };

  const handlePreset = (preset) => {
    setMetrics(PRESETS[preset]);
    setResult(null);
    setError(null);
  };

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const payload = Object.fromEntries(
        Object.entries(metrics).map(([k, v]) => [k, Number(v)])
      );
      const data = await apiFetch("/predict", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(data);
    } catch (e) {
      setError(e.message === "Failed to fetch"
        ? "Cannot reach the backend. Ensure FastAPI is running."
        : e.message);
    } finally {
      setLoading(false);
    }
  };

  const FIELDS = [
    { name: "cpu",            label: "CPU Usage",      unit: "%" },
    { name: "memory",         label: "Memory Usage",   unit: "%" },
    { name: "request_rate",   label: "Request Rate",   unit: "req/s" },
    { name: "latency",        label: "Latency",        unit: "ms" },
    { name: "error_rate",     label: "Error Rate",     unit: "%", step: "0.1" },
    { name: "db_connections", label: "DB Connections", unit: "" },
  ];

  const prob = result ? Number(result.probability) : null;
  const isIncident = result?.prediction === 1;

  return (
    <div>
      <div className="page-topbar">
        <div>
          <h2 className="section-title">Incident Prediction</h2>
          <p className="section-subtitle">Enter telemetry values to run the ML model</p>
        </div>
        {modelInfo?.available && (
          <span className="tag">
            {modelInfo.model_type} · {modelInfo.features?.length} features
          </span>
        )}
        {modelInfo?.available === false && (
          <span className="badge badge-high">MODEL UNAVAILABLE</span>
        )}
      </div>

      {/* Preset buttons */}
      <div className="flex-row gap-8 mb-16">
        <span className="text-sm text-muted">Presets:</span>
        {Object.keys(PRESETS).map((name) => (
          <button key={name} className="btn btn-secondary btn-sm" onClick={() => handlePreset(name)}>
            {name}
          </button>
        ))}
      </div>

      {/* Metric inputs */}
      <div className="metrics-grid" style={{ marginBottom: 20 }}>
        {FIELDS.map(({ name, label, unit, step }) => (
          <div className="metric-input-card" key={name}>
            <label htmlFor={`field-${name}`}>{label}</label>
            <div className="metric-input-row">
              <input
                id={`field-${name}`}
                type="number"
                name={name}
                value={metrics[name]}
                onChange={handleChange}
                step={step || "1"}
              />
              <span className="metric-unit-label">{unit || "count"}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Action row */}
      <div className="flex-row" style={{ paddingTop: 16, borderTop: "1px solid var(--border-subtle)", marginBottom: 8 }}>
        <span className="text-sm text-secondary">Model: Random Forest Classifier</span>
        <button
          className="btn btn-primary"
          onClick={handlePredict}
          disabled={loading || modelInfo?.available === false}
          style={{ marginLeft: "auto" }}
        >
          {loading ? <><RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} /> Analyzing...</> : <>Run Prediction →</>}
        </button>
      </div>

      {error && <AlertBox type="error" title="Prediction failed">{error}</AlertBox>}

      {/* Result */}
      {result && (
        <div className={`result-banner ${isIncident ? "incident" : "normal"}`}>
          <div className="flex-row gap-12 mb-16">
            {isIncident
              ? <AlertTriangle size={22} color="var(--color-high)" />
              : <CheckCircle size={22} color="var(--color-low)" />
            }
            <h2 className="result-headline" style={{ marginBottom: 0 }}>
              {isIncident ? "Incident Predicted" : "System Normal"}
            </h2>
            {riskBadge(result.risk_level)}
          </div>

          <div className="result-meta-grid">
            <div className="result-meta-tile">
              <p className="tile-label">Incident Probability</p>
              <p className="tile-value">{(prob * 100).toFixed(1)}%</p>
              <div className="prob-bar-track">
                <div
                  className={`prob-bar-fill ${result.risk_level?.toLowerCase()}`}
                  style={{ width: `${(prob * 100).toFixed(1)}%` }}
                />
              </div>
            </div>
            <div className="result-meta-tile">
              <p className="tile-label">Risk Level</p>
              <p className="tile-value">{result.risk_level}</p>
            </div>
          </div>

          {result.risk_override && (
            <AlertBox type="warning" title="Risk override applied">
              {result.risk_override}
            </AlertBox>
          )}

          {/* Contributing factors */}
          {result.contributing_factors?.length > 0 && (
            <div className="mt-16">
              <p className="text-sm text-muted mb-8">
                <strong style={{ color: "var(--text-secondary)" }}>Top Contributing Features</strong>
                <span className="text-secondary"> (by model feature importance)</span>
              </p>
              <div className="flex-row flex-wrap gap-8">
                {result.contributing_factors.map((f, i) => (
                  <span key={f} className="badge badge-info">
                    {i + 1}. {f.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Anomalies */}
          <div className="mt-16">
            <p className="text-sm mb-8" style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
              Detected Anomalies ({result.anomalies?.length ?? 0})
            </p>
            {result.anomalies?.length > 0 ? (
              <div className="anomaly-list">
                {result.anomalies.map((a) => (
                  <div key={a.metric} className={`anomaly-item ${a.severity?.toLowerCase()}`}>
                    <div>
                      <span className="anomaly-metric">{a.metric.replaceAll("_", " ")}</span>
                      <br />
                      <span className="badge badge-high" style={{ marginTop: 4, fontSize: 9 }}>{a.severity}</span>
                    </div>
                    <span className="anomaly-message">{a.message}</span>
                    <span className="text-mono" style={{ color: "var(--text-accent)", whiteSpace: "nowrap" }}>
                      {fmt(a.value)}{a.unit}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No threshold anomalies detected.</p>
            )}
          </div>

          {result.active_incident_id && (
            <p className="text-sm text-secondary mt-12">
              <span className="text-mono" style={{ color: "var(--text-accent)" }}>
                Active Incident #{result.active_incident_id}
              </span>
              {" "}created or updated in the incident tracker.
            </p>
          )}
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// VIEW: INCIDENTS
// ═══════════════════════════════════════════════════════════════
function IncidentDetailPanel({ incident, onClose, onStatusChange }) {
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState(null);
  const [notes, setNotes] = useState("");

  if (!incident) return null;

  const transitions = {
    OPEN: ["ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED"],
    ACKNOWLEDGED: ["INVESTIGATING", "RESOLVED", "CLOSED"],
    INVESTIGATING: ["RESOLVED", "CLOSED"],
    RESOLVED: ["CLOSED"],
    CLOSED: [],
  }[incident.status] || [];

  const doTransition = async (status) => {
    setUpdating(true);
    setUpdateError(null);
    try {
      await apiFetch(`/active-incidents/${incident.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, resolution_notes: notes || undefined }),
      });
      onStatusChange();
    } catch (e) {
      setUpdateError(e.message);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="detail-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="detail-panel">
        <div className="flex-row" style={{ marginBottom: 24 }}>
          <h2 className="section-title" style={{ flex: 1 }}>
            Incident #{incident.id}
          </h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="flex-row gap-8 mb-16">
          {riskBadge(incident.risk_level)}
          {statusBadge(incident.status)}
          <span className="text-sm text-muted">×{incident.occurrence_count}</span>
        </div>

        <hr className="separator" />

        <div className="three-col" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div>
            <p className="text-sm text-muted mb-4">First seen</p>
            <p className="text-sm">{relTime(incident.first_seen)}</p>
          </div>
          <div>
            <p className="text-sm text-muted mb-4">Last seen</p>
            <p className="text-sm">{relTime(incident.last_seen)}</p>
          </div>
          <div>
            <p className="text-sm text-muted mb-4">Probability</p>
            <p className="text-sm text-accent">{(incident.probability * 100).toFixed(1)}%</p>
          </div>
          <div>
            <p className="text-sm text-muted mb-4">Prediction</p>
            <p className="text-sm">{incident.prediction === 1 ? "Incident" : "Normal"}</p>
          </div>
        </div>

        {/* Telemetry snapshot */}
        <div className="mt-16">
          <p className="text-sm" style={{ fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
            Telemetry Snapshot
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {incident.telemetry && Object.entries(incident.telemetry).map(([k, v]) => (
              <div key={k} className="card" style={{ padding: "10px 14px" }}>
                <p className="text-sm text-muted">{k.replaceAll("_", " ")}</p>
                <p className="text-mono" style={{ fontSize: 14, color: "var(--text-accent)" }}>{fmt(v)}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Anomalies */}
        {incident.anomalies?.length > 0 && (
          <div className="mt-16">
            <p className="text-sm" style={{ fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
              Anomalies ({incident.anomalies.length})
            </p>
            <div className="anomaly-list">
              {incident.anomalies.map((a) => (
                <div key={a.metric} className={`anomaly-item ${a.severity?.toLowerCase()}`}>
                  <div>
                    <span className="anomaly-metric">{a.metric}</span>
                    <br />
                    <span className="badge badge-high" style={{ marginTop: 4, fontSize: 9 }}>{a.severity}</span>
                  </div>
                  <span className="anomaly-message">{a.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {incident.risk_override && (
          <AlertBox type="warning" title="Risk override">{incident.risk_override}</AlertBox>
        )}

        {/* Status transitions */}
        {transitions.length > 0 && (
          <div className="mt-24">
            <p className="text-sm" style={{ fontWeight: 600, color: "var(--text-secondary)", marginBottom: 10 }}>
              Update Status
            </p>
            {(incident.status === "INVESTIGATING" || incident.status === "ACKNOWLEDGED") && (
              <textarea
                placeholder="Resolution notes (optional)"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                style={{
                  width: "100%", marginBottom: 10, background: "var(--bg-raised)",
                  border: "1px solid var(--border-normal)", color: "var(--text-primary)",
                  borderRadius: 8, padding: "10px 12px", fontSize: 13, resize: "vertical",
                  minHeight: 70,
                }}
              />
            )}
            <div className="flex-row flex-wrap gap-8">
              {transitions.map((status) => (
                <button
                  key={status}
                  className="btn btn-secondary btn-sm"
                  onClick={() => doTransition(status)}
                  disabled={updating}
                >
                  → {status}
                </button>
              ))}
            </div>
            {updateError && <AlertBox type="error">{updateError}</AlertBox>}
          </div>
        )}
      </div>
    </div>
  );
}

function IncidentsView() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [riskFilter, setRiskFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState(null);
  const LIMIT = 20;

  const fetchIncidents = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: LIMIT,
        offset: page * LIMIT,
        ...(statusFilter && { status: statusFilter }),
        ...(riskFilter && { risk_level: riskFilter }),
      });
      const data = await apiFetch(`/active-incidents?${params}`);
      setIncidents(data.incidents || []);
      setTotal(data.count || 0);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, riskFilter]);

  useEffect(() => { fetchIncidents(); }, [fetchIncidents]);

  const filtered = incidents.filter((inc) =>
    !search || String(inc.id).includes(search)
  );

  const handleStatusChange = () => {
    fetchIncidents();
    if (selected) {
      apiFetch(`/active-incidents/${selected.id}`)
        .then((d) => setSelected(d.incident))
        .catch(() => {});
    }
  };

  return (
    <div>
      <div className="page-topbar">
        <div>
          <h2 className="section-title">Incident Management</h2>
          <p className="section-subtitle">Active incident tracker with full lifecycle management</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchIncidents}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <div className="filter-bar">
        <input
          className="filter-input"
          placeholder="Search by ID…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
        />
        <select className="filter-select" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}>
          <option value="">All Statuses</option>
          {["OPEN", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED"].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select className="filter-select" value={riskFilter} onChange={(e) => { setRiskFilter(e.target.value); setPage(0); }}>
          <option value="">All Risk Levels</option>
          {["HIGH", "MEDIUM", "LOW"].map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <span className="tag">{total} incidents</span>
      </div>

      {error && <AlertBox type="error" title="Failed to load incidents">{error}</AlertBox>}

      {loading ? (
        <LoadingPlaceholder rows={6} />
      ) : filtered.length === 0 ? (
        <EmptyState icon="🛡️" message="No incidents match the current filters." />
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Risk</th>
                <th>Status</th>
                <th>Probability</th>
                <th>Anomalies</th>
                <th>Occurrences</th>
                <th>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((inc) => (
                <tr key={inc.id} onClick={() => setSelected(inc)}>
                  <td><span className="text-mono">#{inc.id}</span></td>
                  <td>{riskBadge(inc.risk_level)}</td>
                  <td>{statusBadge(inc.status)}</td>
                  <td>
                    <span className="text-mono" style={{ color: "var(--text-accent)" }}>
                      {(inc.probability * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td>{inc.anomalies?.length ?? 0}</td>
                  <td><strong>{inc.occurrence_count}</strong></td>
                  <td>{relTime(inc.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {total > LIMIT && (
        <div className="flex-row mt-16" style={{ justifyContent: "center", gap: 8 }}>
          <button className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
            ← Prev
          </button>
          <span className="text-sm text-muted">
            Page {page + 1} of {Math.ceil(total / LIMIT)}
          </span>
          <button className="btn btn-secondary btn-sm" disabled={(page + 1) * LIMIT >= total} onClick={() => setPage(p => p + 1)}>
            Next →
          </button>
        </div>
      )}

      {selected && (
        <IncidentDetailPanel
          incident={selected}
          onClose={() => setSelected(null)}
          onStatusChange={handleStatusChange}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// VIEW: ANALYTICS
// ═══════════════════════════════════════════════════════════════
function AnalyticsView() {
  const [trends, setTrends] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    apiFetch("/analytics/trends?limit=200")
      .then((d) => { setTrends(d); setError(null); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const PIE_COLORS = {
    HIGH: "#f87171", MEDIUM: "#fb923c", LOW: "#4ade80",
  };

  if (loading) return <LoadingPlaceholder rows={8} />;
  if (error) return <AlertBox type="error" title="Analytics unavailable">{error}</AlertBox>;

  const riskDist = trends?.risk_distribution || [];
  const anomalyFreq = trends?.anomaly_frequency || [];
  const incidentByDate = trends?.incident_by_date || [];
  const telHistory = trends?.telemetry_history || [];

  return (
    <div>
      <div className="page-topbar">
        <div>
          <h2 className="section-title">Analytics</h2>
          <p className="section-subtitle">Historical trends and distribution analysis</p>
        </div>
      </div>

      <div className="two-col">
        {/* Risk distribution pie */}
        <div className="card">
          <div className="card-header">
            <div>
              <p className="card-title">Risk Distribution</p>
              <p className="card-subtitle">All active incidents by risk level</p>
            </div>
          </div>
          {riskDist.length === 0 ? (
            <EmptyState icon="📊" message="No incident data yet." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={riskDist}
                  dataKey="count"
                  nameKey="risk_level"
                  cx="50%" cy="50%"
                  outerRadius={80}
                  label={({ risk_level, percent }) =>
                    `${risk_level} ${(percent * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                >
                  {riskDist.map((entry) => (
                    <Cell key={entry.risk_level} fill={PIE_COLORS[entry.risk_level] || "#6b7280"} />
                  ))}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Anomaly frequency bar */}
        <div className="card">
          <div className="card-header">
            <div>
              <p className="card-title">Anomaly Frequency</p>
              <p className="card-subtitle">By metric (last 200 predictions)</p>
            </div>
          </div>
          {anomalyFreq.length === 0 ? (
            <EmptyState icon="📊" message="No anomaly data yet." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={anomalyFreq} layout="vertical" margin={{ left: 20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
                <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                <YAxis type="category" dataKey="metric" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} width={100} />
                <Tooltip content={<DarkTooltip />} />
                <Bar dataKey="count" fill="#7b8fff" radius={[0, 4, 4, 0]} name="Count" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Incidents by date */}
      {incidentByDate.length > 0 && (
        <div className="card mt-16">
          <div className="card-header">
            <div>
              <p className="card-title">Incidents Over Time</p>
              <p className="card-subtitle">Active incidents grouped by date and risk level</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={
              Object.values(incidentByDate.reduce((acc, row) => {
                acc[row.date] = acc[row.date] || { date: row.date, HIGH: 0, MEDIUM: 0, LOW: 0 };
                acc[row.date][row.risk_level] = (acc[row.date][row.risk_level] || 0) + row.count;
                return acc;
              }, {}))
            }>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip content={<DarkTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: "var(--text-secondary)" }} />
              <Bar dataKey="HIGH" stackId="a" fill="#f87171" name="High" />
              <Bar dataKey="MEDIUM" stackId="a" fill="#fb923c" name="Medium" />
              <Bar dataKey="LOW" stackId="a" fill="#4ade80" name="Low" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* CPU/Memory historical */}
      {telHistory.length > 0 && (
        <div className="card mt-16">
          <div className="card-header">
            <div>
              <p className="card-title">CPU & Memory History</p>
              <p className="card-subtitle">Stored telemetry snapshots</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={telHistory.map((h) => ({
              time: new Date(h.timestamp).toLocaleDateString(),
              cpu: h.cpu,
              memory: h.memory,
            }))}>
              <defs>
                <linearGradient id="g-cpu" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#7b8fff" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#7b8fff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="time" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} domain={[0, 100]} />
              <Tooltip content={<DarkTooltip />} />
              <Area type="monotone" dataKey="cpu" stroke="#7b8fff" fill="url(#g-cpu)" name="CPU %" dot={false} />
              <Area type="monotone" dataKey="memory" stroke="#a78bfa" fill="transparent" name="Memory %" dot={false} />
              <Legend wrapperStyle={{ fontSize: 11, color: "var(--text-secondary)" }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {riskDist.length === 0 && anomalyFreq.length === 0 && incidentByDate.length === 0 && telHistory.length === 0 && (
        <div className="card mt-16">
          <EmptyState icon="📊" message="No analytics data yet. Run some predictions to populate charts." />
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// VIEW: SETTINGS
// ═══════════════════════════════════════════════════════════════
function SettingsView({ modelInfo }) {
  const [thresholds, setThresholds] = useState(null);
  const [thresholdsError, setThresholdsError] = useState(null);

  useEffect(() => {
    apiFetch("/settings/thresholds")
      .then((d) => setThresholds(d.thresholds))
      .catch((e) => setThresholdsError(e.message));
  }, []);

  return (
    <div>
      <div className="page-topbar">
        <div>
          <h2 className="section-title">Settings & Configuration</h2>
          <p className="section-subtitle">View active configuration — thresholds are read-only in this version</p>
        </div>
      </div>

      {/* Model info */}
      <div className="card card-lg" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <p className="card-title">ML Model</p>
          <span className={modelInfo?.available ? "badge badge-low" : "badge badge-high"}>
            {modelInfo?.available ? "LOADED" : "UNAVAILABLE"}
          </span>
        </div>
        {modelInfo && (
          <>
            <div className="settings-row">
              <span className="settings-key">Model Type</span>
              <span className="settings-value">{modelInfo.model_type || "—"}</span>
            </div>
            <div className="settings-row">
              <span className="settings-key">Features</span>
              <span className="settings-value">{modelInfo.features?.join(", ") || "—"}</span>
            </div>
            <div className="settings-row">
              <span className="settings-key">Estimators</span>
              <span className="settings-value">{modelInfo.n_estimators ?? "—"}</span>
            </div>
            {modelInfo.feature_importances && (
              <div className="mt-16">
                <p className="text-sm text-muted mb-8">Feature Importances (global)</p>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart
                    data={Object.entries(modelInfo.feature_importances).map(([k, v]) => ({
                      feature: k, importance: +(v * 100).toFixed(2),
                    }))}
                    layout="vertical"
                    margin={{ left: 20, right: 20 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 10 }} unit="%" />
                    <YAxis type="category" dataKey="feature" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} width={110} />
                    <Tooltip content={<DarkTooltip />} />
                    <Bar dataKey="importance" fill="#7b8fff" radius={[0, 4, 4, 0]} name="Importance %" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        )}
      </div>

      {/* Thresholds */}
      <div className="card card-lg">
        <div className="card-header">
          <p className="card-title">Anomaly Detection Thresholds</p>
          <span className="badge badge-info">READ-ONLY</span>
        </div>
        {thresholdsError ? (
          <AlertBox type="error">{thresholdsError}</AlertBox>
        ) : thresholds ? (
          <div className="table-container" style={{ border: "none" }}>
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Warning</th>
                  <th>Critical</th>
                  <th>Unit</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(thresholds).map(([metric, cfg]) => (
                  <tr key={metric} style={{ cursor: "default" }}>
                    <td><span className="text-mono">{metric}</span></td>
                    <td><span className="settings-value" style={{ color: "var(--color-med)" }}>{cfg.warning}</span></td>
                    <td><span className="settings-value" style={{ color: "var(--color-high)" }}>{cfg.critical}</span></td>
                    <td>{cfg.unit || "count"}</td>
                    <td>{cfg.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <LoadingPlaceholder rows={3} />
        )}
      </div>

      {/* Environment */}
      <div className="card card-lg mt-16">
        <p className="card-title" style={{ marginBottom: 16 }}>Runtime Configuration</p>
        <div className="settings-row">
          <span className="settings-key">API Base URL</span>
          <span className="settings-value">{API}</span>
        </div>
        <div className="settings-row">
          <span className="settings-key">Frontend Version</span>
          <span className="settings-value">2.0.0</span>
        </div>
        <AlertBox type="info">
          Thresholds and telemetry source are configured via environment variables.
          See <code>.env.example</code> for available options.
        </AlertBox>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// ROOT APP
// ═══════════════════════════════════════════════════════════════
const VIEWS = [
  { id: "overview",    label: "Overview",       icon: LayoutDashboard },
  { id: "monitoring",  label: "Monitoring",      icon: Activity },
  { id: "prediction",  label: "Prediction",      icon: Zap },
  { id: "incidents",   label: "Incidents",       icon: AlertTriangle },
  { id: "analytics",   label: "Analytics",       icon: BarChart3 },
  { id: "settings",    label: "Settings",        icon: Settings },
];

export default function App() {
  const [view, setView] = useState("overview");
  const [telemetry, setTelemetry] = useState(null);
  const [telemetryError, setTelemetryError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [health, setHealth] = useState(null);
  const [modelInfo, setModelInfo] = useState(null);
  const cancelRef = useRef(false);

  // Fetch telemetry on interval — does NOT trigger /predict
  useEffect(() => {
    cancelRef.current = false;

    const fetchTelemetry = async () => {
      try {
        const data = await apiFetch("/telemetry");
        if (!cancelRef.current) {
          setTelemetry(data);
          setTelemetryError(null);
          setLastUpdate(new Date().toLocaleTimeString());
        }
      } catch (e) {
        if (!cancelRef.current) {
          setTelemetryError(e.message === "Failed to fetch"
            ? "Backend unreachable. Is FastAPI running?"
            : e.message);
        }
      }
    };

    fetchTelemetry();
    const id = setInterval(fetchTelemetry, 5000);
    return () => { cancelRef.current = true; clearInterval(id); };
  }, []);

  // Health check
  useEffect(() => {
    apiFetch("/health").then(setHealth).catch(() => {});
    const id = setInterval(() => {
      apiFetch("/health").then(setHealth).catch(() => {});
    }, 30000);
    return () => clearInterval(id);
  }, []);

  // Model info
  useEffect(() => {
    apiFetch("/model/info").then(setModelInfo).catch(() => {});
  }, []);

  const handleSaveSnapshot = async () => {
    try {
      await apiFetch("/telemetry?save=true");
    } catch (e) {
      console.error("Snapshot save failed:", e.message);
    }
  };

  const healthStatus = health?.status;
  const dotClass = healthStatus === "healthy" ? "" : healthStatus === "degraded" ? "degraded" : "error";

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-mark">A</div>
          <span className="sidebar-brand-name">AEGIS<span>.</span></span>
        </div>

        <p className="sidebar-section-label">MONITORING</p>
        <nav className="sidebar-nav">
          {VIEWS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-btn ${view === id ? "active" : ""}`}
              onClick={() => setView(id)}
            >
              <Icon size={15} className="nav-icon" />
              {label}
              {id === "incidents" && health?.components?.database?.ok && (
                <span style={{ marginLeft: "auto" }} />
              )}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="system-status-pill">
            <div className={`pulse-dot ${dotClass}`} />
            <span>{healthStatus ? healthStatus.charAt(0).toUpperCase() + healthStatus.slice(1) : "Connecting"}</span>
          </div>
          {lastUpdate && (
            <p className="text-sm text-muted mt-8">
              Updated {lastUpdate}
            </p>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="main-content">
        <div className="page">
          {/* Page header */}
          <div className="page-header">
            <div className="page-header-left">
              <p className="page-eyebrow">INFRASTRUCTURE INTELLIGENCE</p>
              <h1 className="page-title">
                {VIEWS.find((v) => v.id === view)?.label}
              </h1>
            </div>
            <div className="flex-row gap-12">
              {telemetryError && (
                <span className="badge badge-high">
                  <XCircle size={11} /> Backend offline
                </span>
              )}
              {!telemetryError && lastUpdate && (
                <span className="last-update">⏱ {lastUpdate}</span>
              )}
            </div>
          </div>

          {/* Views */}
          {view === "overview" && (
            <OverviewView telemetry={telemetry} telemetryError={telemetryError} health={health} />
          )}
          {view === "monitoring" && (
            <MonitoringView
              telemetry={telemetry}
              telemetryError={telemetryError}
              onSaveSnapshot={handleSaveSnapshot}
            />
          )}
          {view === "prediction" && (
            <PredictionView modelInfo={modelInfo} />
          )}
          {view === "incidents" && (
            <IncidentsView />
          )}
          {view === "analytics" && (
            <AnalyticsView />
          )}
          {view === "settings" && (
            <SettingsView modelInfo={modelInfo} />
          )}
        </div>
      </main>
    </div>
  );
}
