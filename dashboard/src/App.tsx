import { useEffect, useState } from 'react';
import FixtureTable from './components/FixtureTable';
import AccuracyWidget from './components/AccuracyWidget';
import LivePredictSection from './components/LivePredictSection';
import Section from './components/Section';
import RecentResultsTable from './components/RecentResultsTable';
import PerformanceTracker from './components/PerformanceTracker';
import AccuracyByCategory from './components/AccuracyByCategory';
import CalibrationTable from './components/CalibrationTable';
import PunditSection from './components/PunditSection';
import TrainReport from './components/TrainReport';
import type { Prediction } from './lib/types';

export default function App() {
  const [fixtures, setFixtures] = useState<Prediction[]>([]);

  useEffect(() => {
    fetch('/football/predictions.json')
      .then((r) => r.json())
      .then(setFixtures)
      .catch(() => {
        fetch('/predictions.json').then((r) => r.json()).then(setFixtures);
      });
  }, []);

  return (
    <main>
      <header style={{ marginBottom: '2rem' }}>
        <p style={{
          margin: 0,
          marginBottom: '0.5rem',
          fontSize: '0.85rem',
          textTransform: 'uppercase',
          letterSpacing: '0.12em',
          color: 'var(--accent)',
        }}>
          Premier League
        </p>
        <h1 style={{ margin: 0, fontSize: '2rem' }}>Home-Win Predictions</h1>
      </header>

      <Section title="Model Accuracy">
        <AccuracyWidget />
      </Section>

      <Section title="Upcoming Fixtures">
        <FixtureTable fixtures={fixtures} />
      </Section>

      <Section title="Analysis & Insights">
        <PunditSection />
      </Section>

      <Section title="Recent Results">
        <RecentResultsTable />
      </Section>

      <Section title="Recent Performance">
        <PerformanceTracker />
      </Section>

      <Section title="Accuracy by Category">
        <AccuracyByCategory />
      </Section>

      <Section title="Calibration Analysis">
        <CalibrationTable />
      </Section>

      <Section title="Live Prediction">
        <LivePredictSection />
      </Section>

      <Section title="Model Training Report">
        <TrainReport />
      </Section>

      <footer style={{
        marginTop: '3rem',
        paddingTop: '2rem',
        borderTop: '1px solid var(--panel-border)',
        textAlign: 'center',
        fontSize: '0.875rem',
      }}>
        <p style={{ margin: 0, color: 'var(--muted)' }}>
          Back to{' '}
          <a
            href="https://bashaar.me"
            style={{
              color: 'var(--accent)',
              textDecoration: 'none',
              borderBottom: '1px solid var(--accent)',
            }}
          >
            portfolio
          </a>
        </p>
      </footer>
    </main>
  );
}
