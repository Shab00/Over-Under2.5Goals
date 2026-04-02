set -euo pipefail

log() { echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"; }

log "weekly pipeline start"

log "step: scrape"
python3 jobs/scrape_matches.py

log "step: train"
python3 jobs/train_model.py

log "step: build predictions snapshot"
python3 jobs/build_predictions_snapshot.py

log "step: publish snapshot"
python3 jobs/publish_snapshot.py

log "step: deliver telegram"
python3 jobs/deliver_telegram.py

log "weekly pipeline done"
