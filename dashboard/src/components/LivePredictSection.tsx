import { useState } from 'react';
import { predict } from '../lib/api';
import type { PredictResponse } from '../lib/types';
import SignalBadge from './SignalBadge';
import ConfidenceBar from './ConfidenceBar';

export default function LivePredictSection() {
  const [homeTeam, setHomeTeam] = useState('Arsenal');
  const [awayTeam, setAwayTeam] = useState('Leeds');
  const [oddsHome, setOddsHome] = useState('1.38');
  const [oddsDraw, setOddsDraw] = useState('5.0');
  const [oddsAway, setOddsAway] = useState('8.0');
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handlePredict = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const res = await predict({
        home_team: homeTeam,
        away_team: awayTeam,
        odds_home: parseFloat(oddsHome),
        odds_draw: parseFloat(oddsDraw),
        odds_away: parseFloat(oddsAway),
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginBottom: '2rem' }}>
      <h2 style={{ margin: '0 0 1rem 0', fontSize: '1.5rem' }}>Live Predict</h2>

      <div style={{
        background: 'var(--panel)',
        border: '1px solid var(--panel-border)',
        borderRadius: '8px',
        padding: '1.5rem',
      }}>
        <form onSubmit={handlePredict} style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: '1rem',
          marginBottom: '1rem',
        }}>
          <div>
            <label style={{
              display: 'block',
              fontSize: '0.85rem',
              color: 'var(--muted)',
              marginBottom: '0.4rem',
              textTransform: 'uppercase',
            }}>
              Home Team
            </label>
            <input
              type="text"
              value={homeTeam}
              onChange={(e) => setHomeTeam(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                background: 'var(--panel-border)',
                border: '1px solid var(--panel-border)',
                borderRadius: '4px',
                color: 'var(--text)',
                fontFamily: 'inherit',
              }}
              placeholder="Home team"
            />
          </div>

          <div>
            <label style={{
              display: 'block',
              fontSize: '0.85rem',
              color: 'var(--muted)',
              marginBottom: '0.4rem',
              textTransform: 'uppercase',
            }}>
              Away Team
            </label>
            <input
              type="text"
              value={awayTeam}
              onChange={(e) => setAwayTeam(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                background: 'var(--panel-border)',
                border: '1px solid var(--panel-border)',
                borderRadius: '4px',
                color: 'var(--text)',
                fontFamily: 'inherit',
              }}
              placeholder="Away team"
            />
          </div>

          <div>
            <label style={{
              display: 'block',
              fontSize: '0.85rem',
              color: 'var(--muted)',
              marginBottom: '0.4rem',
              textTransform: 'uppercase',
            }}>
              Odds Home
            </label>
            <input
              type="number"
              value={oddsHome}
              onChange={(e) => setOddsHome(e.target.value)}
              step="0.01"
              min="1"
              style={{
                width: '100%',
                padding: '0.5rem',
                background: 'var(--panel-border)',
                border: '1px solid var(--panel-border)',
                borderRadius: '4px',
                color: 'var(--text)',
                fontFamily: 'inherit',
              }}
              placeholder="1.38"
            />
          </div>

          <div>
            <label style={{
              display: 'block',
              fontSize: '0.85rem',
              color: 'var(--muted)',
              marginBottom: '0.4rem',
              textTransform: 'uppercase',
            }}>
              Odds Draw
            </label>
            <input
              type="number"
              value={oddsDraw}
              onChange={(e) => setOddsDraw(e.target.value)}
              step="0.01"
              min="1"
              style={{
                width: '100%',
                padding: '0.5rem',
                background: 'var(--panel-border)',
                border: '1px solid var(--panel-border)',
                borderRadius: '4px',
                color: 'var(--text)',
                fontFamily: 'inherit',
              }}
              placeholder="5.0"
            />
          </div>

          <div>
            <label style={{
              display: 'block',
              fontSize: '0.85rem',
              color: 'var(--muted)',
              marginBottom: '0.4rem',
              textTransform: 'uppercase',
            }}>
              Odds Away
            </label>
            <input
              type="number"
              value={oddsAway}
              onChange={(e) => setOddsAway(e.target.value)}
              step="0.01"
              min="1"
              style={{
                width: '100%',
                padding: '0.5rem',
                background: 'var(--panel-border)',
                border: '1px solid var(--panel-border)',
                borderRadius: '4px',
                color: 'var(--text)',
                fontFamily: 'inherit',
              }}
              placeholder="8.0"
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%',
                padding: '0.5rem',
                background: loading ? 'var(--muted)' : 'var(--accent)',
                color: loading ? 'var(--muted)' : '#000',
                border: 'none',
                borderRadius: '4px',
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'background 0.2s',
              }}
              onMouseEnter={(e) => !loading && (e.currentTarget.style.background = 'var(--accent-hover)')}
              onMouseLeave={(e) => !loading && (e.currentTarget.style.background = 'var(--accent)')}
            >
              {loading ? 'Predicting...' : 'Predict'}
            </button>
          </div>
        </form>

        {error && (
          <div style={{
            padding: '0.75rem',
            background: 'var(--red)',
            borderRadius: '4px',
            color: '#fff',
            fontSize: '0.9rem',
            marginBottom: '1rem',
          }}>
            {error}
          </div>
        )}

        {result && (
          <div style={{
            background: 'var(--panel-border)',
            borderRadius: '8px',
            padding: '1rem',
            marginTop: '1rem',
          }}>
            <div style={{ display: 'grid', gap: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--muted)' }}>Match</p>
                  <p style={{ margin: '0.25rem 0 0 0', fontSize: '1.1rem', fontWeight: 600 }}>
                    {result.home_team} vs {result.away_team}
                  </p>
                </div>
                <SignalBadge category={result.betting_category} />
              </div>

              <div>
                <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: 'var(--muted)' }}>
                  Home Win Probability
                </p>
                <ConfidenceBar value={result.prob_homewin} />
              </div>

              <div>
                <p style={{ margin: '0 0 0.25rem 0', fontSize: '0.9rem', color: 'var(--muted)' }}>
                  Signal
                </p>
                <p style={{ margin: 0, fontSize: '1rem' }}>{result.signal}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
