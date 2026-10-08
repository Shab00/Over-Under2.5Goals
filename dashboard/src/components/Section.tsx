import React from 'react';

interface SectionProps {
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
}

export default function Section({ title, eyebrow, children }: SectionProps) {
  return (
    <section
      style={{
        marginBottom: '2rem',
      }}
    >
      {eyebrow && (
        <div
          style={{
            fontSize: '0.75rem',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--accent)',
            marginBottom: '0.5rem',
            fontWeight: 600,
          }}
        >
          {eyebrow}
        </div>
      )}
      <h2
        style={{
          fontSize: '1.5rem',
          fontWeight: 700,
          margin: '0 0 1rem 0',
          color: 'var(--text)',
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}
