import { useEffect, useState } from 'react';
import { fetchPundit } from '../lib/queries';
import type { Pundit } from '../lib/types';

interface FixtureItemProps {
  home_team?: string;
  away_team?: string;
  signal?: string;
  confidence?: string;
  pundit_action?: string;
}

function FixtureItem({
  home_team,
  away_team,
  signal,
  confidence,
  pundit_action,
}: FixtureItemProps) {
  return (
    <div
      style={{
        background: 'rgba(56, 189, 248, 0.05)',
        border: '1px solid var(--panel-border)',
        borderRadius: '8px',
        padding: '0.75rem',
        marginBottom: '0.5rem',
      }}
    >
      <div style={{ fontWeight: 600, color: 'var(--text)' }}>
        {home_team} vs {away_team}
      </div>
      {signal && (
        <div style={{ fontSize: '0.875rem', color: 'var(--accent)', marginTop: '0.25rem' }}>
          Signal: <strong>{signal}</strong>
        </div>
      )}
      {confidence && (
        <div style={{ fontSize: '0.875rem', color: 'var(--muted)', marginTop: '0.25rem' }}>
          Confidence: {confidence}
        </div>
      )}
      {pundit_action && (
        <div
          style={{
            fontSize: '0.875rem',
            color: 'var(--green)',
            marginTop: '0.25rem',
            fontWeight: 600,
          }}
        >
          Action: {pundit_action}
        </div>
      )}
    </div>
  );
}

export default function PunditSection() {
  const [pundit, setPundit] = useState<Pundit | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPundit()
      .then((data) => {
        setPundit(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to fetch pundit data');
        setPundit(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)' }}>
        Loading pundit analysis...
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

  if (!pundit) {
    return (
      <div style={{ color: 'var(--muted)' }}>
        No pundit data available.
      </div>
    );
  }

  return (
    <div>
      {/* Model Form */}
      <div
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--panel-border)',
          borderRadius: '16px',
          padding: '1.5rem',
          marginBottom: '1.5rem',
        }}
      >
        <h3
          style={{
            fontSize: '1.25rem',
            fontWeight: 700,
            color: 'var(--accent)',
            margin: '0 0 1rem 0',
          }}
        >
          {pundit.model_form}
        </h3>
      </div>

      {/* Gameweek Summary */}
      <div
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--panel-border)',
          borderRadius: '16px',
          padding: '1.5rem',
          marginBottom: '1.5rem',
        }}
      >
        <h4
          style={{
            fontSize: '1rem',
            fontWeight: 700,
            color: 'var(--text)',
            margin: '0 0 0.75rem 0',
            textTransform: 'uppercase',
            fontSize: '0.875rem',
            color: 'var(--accent)',
            letterSpacing: '0.08em',
          }}
        >
          Gameweek Summary
        </h4>
        <p style={{ color: 'var(--muted)', lineHeight: 1.6, margin: 0 }}>
          {pundit.gameweek_summary}
        </p>
      </div>

      {/* Rest of Card */}
      <div
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--panel-border)',
          borderRadius: '16px',
          padding: '1.5rem',
          marginBottom: '1.5rem',
        }}
      >
        <h4
          style={{
            fontSize: '0.875rem',
            fontWeight: 700,
            color: 'var(--accent)',
            margin: '0 0 0.75rem 0',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          Analysis
        </h4>
        <p style={{ color: 'var(--muted)', lineHeight: 1.6, margin: 0 }}>
          {pundit.rest_of_card_paragraph}
        </p>
      </div>

      {/* Top Picks */}
      {pundit.top_picks && pundit.top_picks.length > 0 && (
        <div
          style={{
            background: 'var(--panel)',
            border: '1px solid var(--panel-border)',
            borderRadius: '16px',
            padding: '1.5rem',
            marginBottom: '1.5rem',
          }}
        >
          <h4
            style={{
              fontSize: '0.875rem',
              fontWeight: 700,
              color: 'var(--accent)',
              margin: '0 0 1rem 0',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            Top Picks
          </h4>
          {pundit.top_picks.map((pick, idx) => (
            <FixtureItem key={idx} {...pick} />
          ))}
        </div>
      )}

      {/* Strong Fades */}
      {pundit.strong_fades && pundit.strong_fades.length > 0 && (
        <div
          style={{
            background: 'var(--panel)',
            border: '1px solid var(--panel-border)',
            borderRadius: '16px',
            padding: '1.5rem',
          }}
        >
          <h4
            style={{
              fontSize: '0.875rem',
              fontWeight: 700,
              color: 'var(--red)',
              margin: '0 0 1rem 0',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            Strong Fades
          </h4>
          {pundit.strong_fades.map((fade, idx) => (
            <FixtureItem key={idx} {...fade} />
          ))}
        </div>
      )}
    </div>
  );
}
