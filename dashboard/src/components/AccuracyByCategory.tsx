import { useEffect, useState } from 'react';
import { fetchCategoryStats } from '../lib/queries';
import type { CategoryStats } from '../lib/types';

const th: React.CSSProperties = {
  textAlign: 'left',
  padding: '0.75rem',
  fontSize: '0.875rem',
  fontWeight: 600,
  color: 'var(--muted)',
  borderBottom: '1px solid var(--panel-border)',
};

const td: React.CSSProperties = {
  padding: '0.75rem',
  borderBottom: '1px solid var(--panel-border)',
};

export default function AccuracyByCategory() {
  const [stats, setStats] = useState<CategoryStats[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCategoryStats()
      .then((data) => {
        setStats(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to fetch category stats');
        setStats(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '1rem' }}>
        Loading category statistics...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ color: 'var(--red)', textAlign: 'center', padding: '1rem' }}>
        Error: {error}
      </div>
    );
  }

  if (!stats || stats.length === 0) {
    return (
      <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '1rem' }}>
        No category statistics available.
      </div>
    );
  }

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--panel-border)',
        borderRadius: '16px',
        overflow: 'hidden',
      }}
    >
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: 'rgba(15, 23, 42, 0.6)' }}>
            <th style={th}>Category</th>
            <th style={th}>Count</th>
            <th style={th}>Correct</th>
            <th style={th}>Accuracy %</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((stat, idx) => (
            <tr key={idx}>
              <td style={td}>
                <strong>{stat.category}</strong>
              </td>
              <td style={td}>{stat.total}</td>
              <td style={td}>{stat.correct}</td>
              <td
                style={{
                  ...td,
                  color: stat.accuracy >= 50 ? 'var(--green)' : 'var(--red)',
                  fontWeight: 600,
                }}
              >
                {stat.accuracy.toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
