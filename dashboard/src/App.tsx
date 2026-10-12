import { useEffect, useState } from 'react';
import FixtureTable from './components/FixtureTable';
import AccuracyWidget from './components/AccuracyWidget';
import LivePredictSection from './components/LivePredictSection';
import PunditSection from './components/PunditSection';
import RecentResultsTable from './components/RecentResultsTable';
import PerformanceTracker from './components/PerformanceTracker';
import AccuracyByCategory from './components/AccuracyByCategory';
import CalibrationTable from './components/CalibrationTable';
import TrainReportComponent from './components/TrainReport';
import { fetchFixtures } from './lib/queries';
import type { Prediction } from './lib/types';

export default function App() {
  const [fixtures, setFixtures] = useState<Prediction[]>([]);

  useEffect(() => {
    fetchFixtures()
      .then((data) => {
        console.log('FIXTURES RECEIVED:', data?.length, data);
        setFixtures(data ?? []);
      })
      .catch((err) => console.error('FIXTURES FAILED:', err));
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

      <section style={{ marginBottom: '2rem' }}>
        <AccuracyWidget />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.4rem' }}>Upcoming Fixtures</h2>
        <FixtureTable fixtures={fixtures} />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <PunditSection />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.4rem' }}>Recent Results</h2>
        <RecentResultsTable />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.4rem' }}>Recent Performance</h2>
        <PerformanceTracker />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.4rem' }}>Accuracy by Category</h2>
        <AccuracyByCategory />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.4rem' }}>Calibration Analysis</h2>
        <CalibrationTable />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <LivePredictSection />
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <TrainReportComponent />
      </section>

      <footer style={{ marginTop: '3rem', paddingTop: '2rem', borderTop: '1px solid var(--panel-border)' }}>
        <a
          href="https://shab00.github.io/"
          style={{ color: 'var(--accent)', textDecoration: 'none', fontSize: '0.9rem' }}
        >
          ← Back to portfolio
        </a>
      </footer>
    </main>
  );
}
