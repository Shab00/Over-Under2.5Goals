import type { Prediction } from '../lib/types';
import SignalBadge from './SignalBadge';
import ConfidenceBar from './ConfidenceBar';

interface Props {
  fixtures: Prediction[];
}

export default function FixtureTable({ fixtures }: Props) {
  if (!fixtures.length) {
    return <p style={{ color: 'var(--muted)' }}>No fixtures available.</p>;
  }

  return (
    <div style={{
      background: 'var(--panel)',
      border: '1px solid var(--panel-border)',
      borderRadius: '16px',
      overflow: 'hidden',
    }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: 'rgba(15, 23, 42, 0.6)' }}>
            <th style={th}>Kickoff</th>
            <th style={th}>Fixture</th>
            <th style={th}>P(Home)</th>
            <th style={th}>Odds</th>
            <th style={th}>Signal</th>
          </tr>
        </thead>
        <tbody>
          {fixtures.map((f) => (
            <tr key={f.match_key} style={{ borderTop: '1px solid var(--panel-border)' }}>
              <td style={td}>
                {new Date(f.kickoff_time_utc).toLocaleString('en-GB', {
                  weekday: 'short',
                  day: 'numeric',
                  month: 'short',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </td>
              <td style={td}>
                <strong>{f.home_team}</strong> vs {f.away_team}
              </td>
              <td style={{ ...td, minWidth: '140px' }}>
                <ConfidenceBar value={f.prob_homewin} />
              </td>
              <td style={td}>{f.odds_B365H.toFixed(2)}</td>
              <td style={td}>
                <SignalBadge category={f.betting_category} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = {
  padding: '0.75rem 1rem',
  textAlign: 'left',
  fontSize: '0.75rem',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: 'var(--muted)',
  fontWeight: 600,
};

const td: React.CSSProperties = {
  padding: '0.85rem 1rem',
  fontSize: '0.9rem',
};
