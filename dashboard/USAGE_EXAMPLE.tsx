/**
 * Usage Example: Complete Dashboard Layout
 * 
 * This file demonstrates how to use all the new dashboard components
 * together in a coordinated dashboard layout.
 * 
 * Components created:
 * - Section.tsx (wrapper)
 * - RecentResultsTable.tsx
 * - PerformanceTracker.tsx
 * - AccuracyByCategory.tsx
 * - CalibrationTable.tsx
 * - PunditSection.tsx
 * - TrainReport.tsx
 */

import React from 'react';

// Import all new components
import Section from './src/components/Section';
import RecentResultsTable from './src/components/RecentResultsTable';
import PerformanceTracker from './src/components/PerformanceTracker';
import AccuracyByCategory from './src/components/AccuracyByCategory';
import CalibrationTable from './src/components/CalibrationTable';
import PunditSection from './src/components/PunditSection';
import TrainReport from './src/components/TrainReport';

export default function CompleteDashboard() {
  return (
    <div>
      {/* Hero / Header Section */}
      <Section title="Model Performance" eyebrow="Live Metrics">
        <PerformanceTracker />
      </Section>

      {/* Training Report */}
      <Section title="Training Status" eyebrow="Latest Model">
        <TrainReport />
      </Section>

      {/* Recent Results */}
      <Section title="Recent Results" eyebrow="Prediction Accuracy">
        <RecentResultsTable />
      </Section>

      {/* Category Breakdown */}
      <Section title="Accuracy by Category" eyebrow="Performance Analysis">
        <AccuracyByCategory />
      </Section>

      {/* Calibration Analysis */}
      <Section title="Model Calibration" eyebrow="Confidence Quality">
        <CalibrationTable />
      </Section>

      {/* Weekly Pundit Analysis */}
      <Section title="This Week's Analysis" eyebrow="Gameweek Insights">
        <PunditSection />
      </Section>
    </div>
  );
}

/**
 * Layout Notes:
 * 
 * 1. PerformanceTracker renders as a 3-column grid (auto-fit, min 250px)
 *    - Adapts to screen size automatically
 * 
 * 2. TrainReport is compact single-panel with inline metrics
 *    - Fits nicely above main tables
 * 
 * 3. RecentResultsTable is full-width table
 *    - Responsive via CSS overflow and border-radius
 * 
 * 4. AccuracyByCategory and CalibrationTable are similar full-width tables
 *    - Stack vertically on mobile
 * 
 * 5. PunditSection expands with multiple panels
 *    - Model form, gameweek summary, analysis, top picks, strong fades
 *    - Responsive padding and typography
 * 
 * CSS Variables Used (from index.css):
 * --bg, --panel, --panel-border, --text, --muted, --accent, --green, --amber, --red
 * 
 * Data Sources (from src/lib/queries.ts):
 * - fetchRecentResults(10)      → Result[]
 * - fetchRolling()              → RollingStats
 * - fetchCategoryStats()        → CategoryStats[]
 * - fetchCalibration()          → CalibrationBucket[]
 * - fetchPundit()               → Pundit
 * - fetchTrainReport()          → TrainReport
 * 
 * All components handle:
 * - Loading state (gray text)
 * - Error state (red error message)
 * - Null/undefined data (graceful message)
 * - TypeScript types (fully typed)
 * - CSS variables (theme-aware)
 */

/**
 * Alternative Layouts:
 * 
 * 1. Compact Dashboard:
 *    Just use: PerformanceTracker, TrainReport, RecentResultsTable, PunditSection
 * 
 * 2. Full Analysis Dashboard:
 *    Use all 7 components as shown above
 * 
 * 3. Mobile-First:
 *    All components are responsive. Tables use horizontal scroll on mobile.
 *    Grids stack to single column on small screens.
 * 
 * 4. Metrics Focus:
 *    Lead with PerformanceTracker, then TrainReport, then PunditSection
 *    Skip detailed tables for summary-only view
 */
