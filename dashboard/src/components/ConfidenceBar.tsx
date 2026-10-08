interface Props {
  value: number; // 0..1
}

export default function ConfidenceBar({ value }: Props) {
  const pct = Math.round(value * 100);
  const colour =
    value >= 0.55 ? 'var(--green)' :
    value >= 0.45 ? 'var(--amber)' :
    value >= 0.30 ? 'var(--accent)' :
                    'var(--red)';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <div style={{
        flex: 1,
        height: '6px',
        background: 'var(--panel-border)',
        borderRadius: '3px',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: colour,
          transition: 'width 0.3s ease',
        }} />
      </div>
      <span style={{ fontSize: '0.85rem', color: 'var(--muted)', minWidth: '40px' }}>
        {pct}%
      </span>
    </div>
  );
}
