interface Props {
  category: string;
}

const LABELS: Record<string, { text: string; colour: string }> = {
  back_home:     { text: 'Back Home',     colour: 'var(--green)' },
  avoid:         { text: 'Avoid',         colour: 'var(--amber)' },
  double_chance: { text: 'Double Chance', colour: 'var(--accent)' },
  strong_fade:   { text: 'Strong Fade',   colour: 'var(--red)' },
};

export default function SignalBadge({ category }: Props) {
  const label = LABELS[category] ?? { text: category, colour: 'var(--muted)' };
  return (
    <span style={{
      display: 'inline-block',
      padding: '0.2rem 0.65rem',
      borderRadius: '999px',
      fontSize: '0.75rem',
      fontWeight: 600,
      color: label.colour,
      border: `1px solid ${label.colour}`,
      background: `${label.colour}1a`,
    }}>
      {label.text}
    </span>
  );
}
