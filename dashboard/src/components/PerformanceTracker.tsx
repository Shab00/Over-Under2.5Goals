import { useEffect, useState } from 'react';
import { fetchRolling } from '../lib/queries';
import type { RollingStats } from '../lib/types';

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

export default function PerformanceTracker() {
  const [stats, setStats] = useState<RollingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRolling()
      .then((data) => {
        setStats(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to fetch rolling stats');
        setStats(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)' }}>
        Loading performance data...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ color: 'var(--red)' }}>
        Error: {error}
      </div>
    );
  }

  if (!stats) {
    return (
      <div style={{ color: 'var(--muted)' }}>
        No performance data available.
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: '1.5rem',
      }}
    >
      <div
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--panel-border)',
          borderRadius: '16px',
          padding: '1.5rem',
        }}
      >
        <div
          style={{
            fontSize: '0.875rem',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--accent)',
            marginBottom: '1rem',
            fontWeight: 600,
          }}
        >
          Last 10 Matches
        </div>
        <StatItem
          label="Accuracy"
          value={stats.last_10_accuracy}
          isPercentage
        />
        <StatItem
          label="Wins / Total"
          value={Math.round((stats.last_10_accuracy * stats.last_10_count) / 100)}
        />
        <StatItem
          label="Total Predictions"
          value={stats.last_10_count}
        />
        <StatItem
          label="Profit/Loss"
          value={stats.last_10_profit}
          isProfitLoss
        />
      </div>

      <div
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--panel-border)',
          borderRadius: '16px',
          padding: '1.5rem',
        }}
      >
        <div
          style={{
            fontSize: '0.875rem',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--accent)',
            marginBottom: '1rem',
            fontWeight: 600,
          }}
        >
          Last 20 Matches
        </div>
        <StatItem
          label="Accuracy"
          value={stats.last_20_accuracy}
          isPercentage
        />
        <StatItem
          label="Wins / Total"
          value={Math.round((stats.last_20_accuracy * stats.last_20_count) / 100)}
        />
        <StatItem
          label="Total Predictions"
          value={stats.last_20_count}
        />
        <StatItem
          label="Profit/Loss"
          value={stats.last_20_profit}
          isProfitLoss
        />
      </div>

      <div
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--panel-border)',
          borderRadius: '16px',
          padding: '1.5rem',
        }}
      >
        <div
          style={{
            fontSize: '0.875rem',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--accent)',
            marginBottom: '1rem',
            fontWeight: 600,
          }}
        >
          Total
        </div>
        <StatItem
          label="Accuracy"
          value={stats.total_accuracy}
          isPercentage
        />
        <StatItem
          label="Wins / Total"
          value={Math.round((stats.total_accuracy * stats.total_count) / 100)}
        />
        <StatItem
          label="Total Predictions"
          value={stats.total_count}
        />
        <StatItem
          label="Profit/Loss"
          value={stats.total_profit}
          isProfitLoss
        />
      </div>
    </div>
  );
}
