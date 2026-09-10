set -euo pipefail

log() { echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"; }

log "weekly pipeline start"

log "step: scrape"
python3 jobs/scrape_matches.py

log "step: train"
python3 jobs/train_model.py

log "step: build features for prediction"
python3 jobs/build_upcoming_features.py

log "step: build predictions snapshot"
python3 jobs/build_predictions_snapshot.py

log "step: publish snapshot"
python3 jobs/publish_snapshot.py

log "step: archive snapshot"
mkdir -p snapshots/archive
cp snapshots/predictions_latest.csv snapshots/archive/predictions_$(date -u +"%Y%m%dT%H%M%S").csv

log "step: deliver telegram"
python3 jobs/deliver_telegram.py

log "step: merge results"
python3 jobs/merge_results.py || true

log "step: update metrics"
curl -s -X POST http://localhost:8000/update_metrics -H "X-API-KEY: ${API_KEY:-test123}" || true

log "weekly pipeline done"

echo "[pipeline] Computing match context..."
python jobs/compute_context.py

echo "[pipeline] Scoring strategy archive..."
python jobs/score_strategy_archive.py

echo "[pipeline] Generating AI pundit strategy..."
python jobs/generate_strategy.py

echo "[pipeline] Delivering strategy to Telegram..."
python jobs/deliver_strategy_telegram.py
