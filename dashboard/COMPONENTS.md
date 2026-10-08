# Dashboard Components

This document describes all the dashboard components created for the Over/Under 2.5 Goals prediction dashboard.

## Components Overview

### 1. **Section.tsx**
Wrapper component for organizing page sections with consistent styling.

**Props:**
- `title` (string) - Required section heading
- `eyebrow` (string, optional) - Small uppercase label above title
- `children` (React.ReactNode) - Section content

**Features:**
- Renders semantic `<section>` element
- Optional eyebrow with accent color styling
- Consistent `mb-2` (2rem) margin bottom
- H2 heading with proper typography
- Reusable for all major page sections

**Example:**
```tsx
<Section title="Recent Results" eyebrow="Past Performance">
  <RecentResultsTable />
</Section>
```

---

### 2. **RecentResultsTable.tsx**
Displays recent match results with prediction accuracy tracking.

**Data Source:** `fetchRecentResults(10)`

**Features:**
- Fetches last 10 match results on mount
- Table columns: Date, Home, Away, Score, Predicted, Actual, Correct?
- Green ✓ / Red ✗ indicators for prediction accuracy
- Graceful error & loading states
- Responsive table with CSS variables styling

**Data Type:** `Result[]`

---

### 3. **PerformanceTracker.tsx**
Multi-window rolling accuracy and profitability tracker.

**Data Source:** `fetchRolling()`

**Features:**
- Displays Last 10, Last 20, and Total stats in grid layout
- Shows per-window:
  - Accuracy percentage
  - Wins / Total predictions count
  - Profit/Loss in units (green if positive, red if negative)
- Responsive 3-column grid (auto-fit minmax 250px)
- Color-coded profit indicators

**Data Type:** `RollingStats`

---

### 4. **AccuracyByCategory.tsx**
Breakdown of prediction accuracy by betting category.

**Data Source:** `fetchCategoryStats()`

**Features:**
- Table showing performance by category:
  - Category name
  - Total predictions
  - Correct predictions
  - Accuracy percentage (green if ≥50%, red if <50%)
- Helps identify weak category areas
- Standard error & loading state handling

**Data Type:** `CategoryStats[]`

---

### 5. **CalibrationTable.tsx**
Calibration analysis showing predicted vs actual accuracy by confidence bucket.

**Data Source:** `fetchCalibration()`

**Features:**
- Table with columns: Confidence Bucket, Count, Predicted %, Actual Accuracy %
- Color-coded calibration quality:
  - **Green** = well-calibrated (<5% difference)
  - **Amber** = acceptable (5-10% difference)
  - **Red** = poor (>10% difference)
- Footer explaining calibration metrics
- Helps validate model confidence intervals

**Data Type:** `CalibrationBucket[]`

---

### 6. **PunditSection.tsx**
Displays pundit/analysis commentary and predictions for the gameweek.

**Data Source:** `fetchPundit()`

**Features:**
- **Model Form** - Bold heading summarizing model status
- **Gameweek Summary** - Weekly analysis paragraph
- **Analysis** - Detailed tactical insights
- **Top Picks** - Strong betting recommendations (if available)
  - Shows team matchup, signal, confidence level, recommended action
  - Green-highlighted action text
- **Strong Fades** - Bets to avoid (if available)
  - Red header for emphasis
  - Same fixture item layout as top picks
- Structured layout with separate panels per section
- Graceful handling of missing lists

**Data Type:** `Pundit`

---

### 7. **TrainReport.tsx**
Displays model training metrics and data details.

**Data Source:** `fetchTrainReport()`

**Features:**
- Inline display with separator dots (·):
  - Accuracy % (green)
  - F1 score (accent color)
  - Feature count
  - Training date (formatted)
- Additional metadata row:
  - Data rows used
  - Test split percentage
  - Team count
  - Form window size
- Compact single-panel design
- Clean typography with color-coded metrics

**Data Type:** `TrainReport`

---

## Styling

All components use CSS variables from `index.css`:

```css
--bg: #0f172a             /* Main background */
--panel: #111827          /* Card/panel background */
--panel-border: #1f2937   /* Card border color */
--text: #e5e7eb           /* Primary text */
--muted: #94a3b8          /* Secondary text */
--accent: #38bdf8         /* Accent highlights */
--accent-hover: #0ea5e9   /* Hover state */
--green: #4ade80          /* Positive/success */
--amber: #fbbf24          /* Warning/caution */
--red: #f87171            /* Negative/error */
```

Common patterns:
- All panels: `background: var(--panel)`, `border: 1px solid var(--panel-border)`, `border-radius: 16px`
- Eyebrows/labels: `color: var(--accent)`, `uppercase`, `0.75rem`, `letter-spacing: 0.08em`
- Tables: borderCollapse, standard padding/spacing
- Success indicators: green text/background
- Error states: red text

---

## Data Fetching

All components use `useEffect` + `useState` pattern:

```tsx
useEffect(() => {
  fetchXXX()
    .then((data) => { setData(data); setError(null); })
    .catch((err) => { setError(err?.message); setData(null); })
    .finally(() => setLoading(false));
}, []);
```

Error handling:
- Loading state: muted gray text
- Error state: red error message
- No data: muted "unavailable" message
- Null checks: Graceful fallbacks

---

## Integration Example

```tsx
import Section from './components/Section';
import RecentResultsTable from './components/RecentResultsTable';
import PerformanceTracker from './components/PerformanceTracker';
import AccuracyByCategory from './components/AccuracyByCategory';
import CalibrationTable from './components/CalibrationTable';
import PunditSection from './components/PunditSection';
import TrainReport from './components/TrainReport';

export default function Dashboard() {
  return (
    <>
      <Section title="Performance" eyebrow="Live Metrics">
        <PerformanceTracker />
      </Section>

      <Section title="Recent Results">
        <RecentResultsTable />
      </Section>

      <Section title="Accuracy by Category">
        <AccuracyByCategory />
      </Section>

      <Section title="Model Calibration">
        <CalibrationTable />
      </Section>

      <Section title="This Week's Analysis">
        <PunditSection />
      </Section>

      <Section title="Model Training">
        <TrainReport />
      </Section>
    </>
  );
}
```

---

## Required JSON Files

Ensure the following files exist in `/public`:

- `predictions.json` - Upcoming fixtures
- `results.json` - Historical match results
- `rolling_stats.json` - Performance windows
- `category_stats.json` - Per-category accuracy
- `calibration.json` - Confidence bucket analysis
- `pundit.json` - Gameweek analysis & picks
- `train_report.json` - Model training metrics

---

## Type Definitions

See `src/lib/types.ts` for interface definitions:

- `Result` - Match result with prediction
- `RollingStats` - Windowed accuracy/profit
- `CategoryStats` - Category-level performance
- `CalibrationBucket` - Confidence vs actual accuracy
- `Pundit` - Gameweek analysis & recommendations
- `TrainReport` - Model metrics & data details

---

## Accessibility & UX

- All tables use standard semantic `<table>` elements
- Color + symbol differentiation (checkmarks, X's, dots)
- Loading states prevent jarring layout shifts
- Error messages are explicit and actionable
- Typography hierarchy maintains visual clarity
- Responsive grid layouts for multi-column panels
