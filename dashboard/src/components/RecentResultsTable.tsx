import { useEffect, useState } from 'react';
import { fetchRecentResults } from '../lib/queries';
import type { Result } from '../lib/types';

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

export default function RecentResultsTable() {
  const [results, setResults] = useState<Result[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRecentResults(10)
      .then((data) => {
        setResults(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to fetch recent results');
        setResults(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '1rem' }}>
        Loading recent results...
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

  if (!results || results.length === 0) {
    return (
      <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '1rem' }}>
        No recent results available.
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
            <th style={th}>Date</th>
            <th style={th}>Home</th>
            <th style={th}>Away</th>
            <th style={th}>Score</th>
            <th style={th}>Predicted</th>
            <th style={th}>Actual</th>
            <th style={th}>Correct?</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => {
            const score =
              r.fthg !== null && r.ftag !== null ? `${r.fthg}-${r.ftag}` : '—';

            const predicted = (() => {
              const p = r.prediction as unknown;
              if (p === true || p === 'true') return 'Home';
              if (p === false || p === 'false') return 'Not Home';
              if (typeof p === 'string' && p.length > 0) return p;
              return '—';
            })();

            const colour =
              r.correct === true
                ? 'var(--green)'
                : r.correct === false
                ? 'var(--red)'
                : 'var(--muted)';

            return (
              <tr key={r.match_key} style={{ borderTop: '1px solid var(--panel-border)' }}>
                <td style={td}>
                  {new Date(r.kickoff_time).toLocaleDateString('en-GB', {
                    weekday: 'short',
                    day: 'numeric',
                    month: 'short',
                  })}
                </td>
                <td style={td}>{r.home_team}</td>
                <td style={td}>{r.away_team}</td>
                <td style={td}>{score}</td>
                <td style={td}>{predicted}</td>
                <td style={td}>{r.ftr ?? '—'}</td>
                <td style={{ ...td, color: colour, fontWeight: 600 }}>
                  {r.correct === true ? '✓' : r.correct === false ? '✗' : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
