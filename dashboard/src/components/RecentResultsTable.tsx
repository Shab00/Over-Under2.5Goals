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
        setError(err?.message || 'Failed to fetch results');
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
          {results.map((result) => (
            <tr key={result.id}>
              <td style={td}>
                {new Date(result.kickoff_time).toLocaleDateString('en-GB', {
                  weekday: 'short',
                  day: 'numeric',
                  month: 'short',
                })}
              </td>
              <td style={td}>{result.home_team}</td>
              <td style={td}>{result.away_team}</td>
              <td style={td}>
                {result.home_goals} - {result.away_goals}
              </td>
              <td style={td}>{result.prediction}</td>
              <td style={td}>
                {result.home_goals + result.away_goals > 2.5 ? 'Over 2.5' : 'Under 2.5'}
              </td>
              <td
                style={{
                  ...td,
                  color: result.correct ? 'var(--green)' : 'var(--red)',
                  fontWeight: 600,
                }}
              >
                {result.correct ? '✓' : '✗'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
