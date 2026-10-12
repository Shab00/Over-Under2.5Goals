import { useEffect, useState } from 'react';
import { fetchRecentResults } from '../lib/queries';
import type { Result } from '../lib/types';

interface StatItemProps {
  label: string;
  value: number;
  isPercentage?: boolean;
  isProfitLoss?: boolean;
}

function StatItem({ label, value, isPercentage, isProfitLoss }: StatItemProps) {
  let displayValue: string;
  let color = 'var(--text)';

  if (isPercentage) {
    displayValue = `${value.toFixed(1)}%`;
  } else if (isProfitLoss) {
    displayValue = value.toFixed(2) + ' units';
    color = value >= 0 ? 'var(--green)' : 'var(--red)';
  } else {
    displayValue = Math.round(value).toString();
  }

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ fontSize: '0.875rem', color: 'var(--muted)', marginBottom: '0.25rem' }}>
        {label}
      </div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color }}>
        {displayValue}
      </div>
    </div>
  );
}

interface WindowStats {
  accuracy: number;
  count: number;
  correct: number;
  profit: number;
}

function computeStats(results: Result[]): WindowStats {
  const scored = results.filter((r) => r.correct !== null);
  const count = scored.length;
  const correct = scored.filter((r) => r.correct === true).length;
  const accuracy = count > 0 ? (correct / count) * 100 : 0;
  const profit = scored.reduce((sum, r) => sum + (r.profit ?? 0), 0);
  return { accuracy, count, correct, profit };
}

export default function PerformanceTracker() {
  const [results, setResults] = useState<Result[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRecentResults(100)
      .then((data) => {
        setResults(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to fetch performance data');
        setResults(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div style={{ color: 'var(--muted)' }}>Loading performance data...</div>;
  }

  if (error) {
    return <div style={{ color: 'var(--red)' }}>Error: {error}</div>;
  }

  if (!results || results.length === 0) {
    return <div style={{ color: 'var(--muted)' }}>No performance data available.</div>;
  }

  // Most recent first — take slices
  const sorted = [...results].sort(
    (a, b) => new Date(b.kickoff_time).getTime() - new Date(a.kickoff_time).getTime()
  );
  const last10 = computeStats(sorted.slice(0, 10));
  const last20 = computeStats(sorted.slice(0, 20));
  const total = computeStats(sorted);

  const cardStyle: React.CSSProperties = {
    background: 'var(--panel)',
    border: '1px solid var(--panel-border)',
    borderRadius: '16px',
    padding: '1.5rem',
  };

  const headingStyle: React.CSSProperties = {
    fontSize: '0.875rem',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    color: 'var(--accent)',
    marginBottom: '1rem',
    fontWeight: 600,
  };

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '1.5rem',
      }}
    >
      <div style={cardStyle}>
        <div style={headingStyle}>Last 10 Matches</div>
        <StatItem label="Accuracy" value={last10.accuracy} isPercentage />
        <StatItem label="Wins / Total" value={last10.correct} />
        <StatItem label="Total Predictions" value={last10.count} />
        <StatItem label="Profit/Loss" value={last10.profit} isProfitLoss />
      </div>

      <div style={cardStyle}>
        <div style={headingStyle}>Last 20 Matches</div>
        <StatItem label="Accuracy" value={last20.accuracy} isPercentage />
        <StatItem label="Wins / Total" value={last20.correct} />
        <StatItem label="Total Predictions" value={last20.count} />
        <StatItem label="Profit/Loss" value={last20.profit} isProfitLoss />
      </div>

      <div style={cardStyle}>
        <div style={headingStyle}>Total</div>
        <StatItem label="Accuracy" value={total.accuracy} isPercentage />
        <StatItem label="Wins / Total" value={total.correct} />
        <StatItem label="Total Predictions" value={total.count} />
        <StatItem label="Profit/Loss" value={total.profit} isProfitLoss />
      </div>
    </div>
  );
}
