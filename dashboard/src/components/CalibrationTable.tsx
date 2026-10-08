import { useEffect, useState } from 'react';
import { fetchCalibration } from '../lib/queries';
import type { CalibrationBucket } from '../lib/types';

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

function getCalibrationColor(predicted: number, actual: number): string {
  const diff = Math.abs(predicted - actual);
  if (diff < 5) return 'var(--green)';
  if (diff < 10) return 'var(--amber)';
  return 'var(--red)';
}

export default function CalibrationTable() {
  const [buckets, setBuckets] = useState<CalibrationBucket[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCalibration()
      .then((data) => {
        setBuckets(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message || 'Failed to fetch calibration data');
        setBuckets(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '1rem' }}>
        Loading calibration data...
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

  if (!buckets || buckets.length === 0) {
    return (
      <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '1rem' }}>
        No calibration data available.
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
            <th style={th}>Confidence Bucket</th>
            <th style={th}>Count</th>
            <th style={th}>Predicted %</th>
            <th style={th}>Actual Accuracy %</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((bucket, idx) => {
            const calibrationColor = getCalibrationColor(
              bucket.predicted_probability * 100,
              bucket.actual_accuracy * 100
            );
            return (
              <tr key={idx}>
                <td style={td}>
                  <strong>{bucket.confidence_range}</strong>
                </td>
                <td style={td}>{bucket.count}</td>
                <td style={td}>
                  {(bucket.predicted_probability * 100).toFixed(1)}%
                </td>
                <td style={{ ...td, color: calibrationColor, fontWeight: 600 }}>
                  {(bucket.actual_accuracy * 100).toFixed(1)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div
        style={{
          padding: '1rem',
          background: 'rgba(15, 23, 42, 0.4)',
          fontSize: '0.875rem',
          color: 'var(--muted)',
          borderTop: '1px solid var(--panel-border)',
        }}
      >
        <strong style={{ color: 'var(--text)' }}>Calibration Quality:</strong> Green = well-calibrated
        (&lt;5% diff), Amber = acceptable (5-10% diff), Red = poor (&gt;10% diff)
      </div>
    </div>
  );
}
