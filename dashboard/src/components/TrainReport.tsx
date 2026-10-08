import { useEffect, useState } from 'react';
import { fetchTrainReport } from '../lib/queries';
import type { TrainReport } from '../lib/types';

export default function TrainReportComponent() {
  const [report, setReport] = useState<TrainReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTrainReport()
      .then((data) => {
        setReport(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to fetch train report');
        setReport(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)' }}>
        Loading training report...
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

  if (!report) {
    return (
      <div style={{ color: 'var(--muted)' }}>
        No training report available.
      </div>
    );
  }

  const trainingDate = new Date(report.created_at_utc).toLocaleDateString('en-GB', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  const accuracyPercent = (report.metrics.accuracy * 100).toFixed(1);
  const f1Score = report.metrics.f1.toFixed(4);

  return (
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
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '1.5rem',
          fontSize: '0.95rem',
          lineHeight: 1.6,
        }}
      >
        <div>
          <span style={{ color: 'var(--muted)' }}>Accuracy:</span>
          <span
            style={{
              color: 'var(--green)',
              fontWeight: 700,
              marginLeft: '0.5rem',
            }}
          >
            {accuracyPercent}%
          </span>
        </div>

        <div style={{ color: 'var(--muted)' }}>·</div>

        <div>
          <span style={{ color: 'var(--muted)' }}>F1:</span>
          <span
            style={{
              color: 'var(--accent)',
              fontWeight: 700,
              marginLeft: '0.5rem',
            }}
          >
            {f1Score}
          </span>
        </div>

        <div style={{ color: 'var(--muted)' }}>·</div>

        <div>
          <span style={{ color: 'var(--muted)' }}>Features:</span>
          <span
            style={{
              color: 'var(--text)',
              fontWeight: 600,
              marginLeft: '0.5rem',
            }}
          >
            {report.features}
          </span>
        </div>

        <div style={{ color: 'var(--muted)' }}>·</div>

        <div>
          <span style={{ color: 'var(--muted)' }}>Trained:</span>
          <span
            style={{
              color: 'var(--text)',
              fontWeight: 600,
              marginLeft: '0.5rem',
            }}
          >
            {trainingDate}
          </span>
        </div>
      </div>

      <div
        style={{
          marginTop: '1rem',
          paddingTop: '1rem',
          borderTop: '1px solid var(--panel-border)',
          fontSize: '0.85rem',
          color: 'var(--muted)',
        }}
      >
        <div>Data: {report.rows_used} rows | Test size: {(report.test_size * 100).toFixed(0)}%</div>
        <div>Teams: {report.teams_count} | Form window: {report.n_matches_form} matches</div>
      </div>
    </div>
  );
}
