import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import type { AccuracyStats } from '../lib/types';

export default function AccuracyWidget() {
  const [stats, setStats] = useState<AccuracyStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    supabase
      .from('public_accuracy')
      .select('*')
      .single()
      .then(({ data, error }) => {
        if (error) setError(error.message);
        else setStats(data);
      });
  }, []);

  if (error) return <Card><span style={{ color: 'var(--red)' }}>DB error: {error}</span></Card>;
  if (!stats) return <Card><span style={{ color: 'var(--muted)' }}>Loading…</span></Card>;

  return (
    <Card>
      <div style={{
        fontSize: '0.75rem',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: 'var(--accent)',
        marginBottom: '0.5rem',
      }}>
        Live model accuracy
      </div>
      <div style={{ fontSize: '2.25rem', fontWeight: 700 }}>
        {stats.accuracy_pct}%
      </div>
      <div style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
        {stats.correct_count} correct of {stats.total_count} scored predictions
      </div>
    </Card>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      background: 'var(--panel)',
      border: '1px solid var(--panel-border)',
      borderRadius: '16px',
      padding: '1.5rem',
    }}>
      {children}
    </div>
  );
}
