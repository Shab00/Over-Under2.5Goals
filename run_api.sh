set -euo pipefail

ENV_NAME=${1:-snapshot-api}

CONDA_BASE=$(conda info --base 2>/dev/null || true)
if [ -z "$CONDA_BASE" ]; then
  echo "conda base not found. Ensure Miniforge is installed and 'conda' is on PATH."
  exit 1
fi
source "${CONDA_BASE}/etc/profile.d/conda.sh"

conda activate "$ENV_NAME" || { echo "Failed to activate env: $ENV_NAME"; exit 2; }

: "${SNAPSHOT_PATH:=$(pwd)/data/processed/predictions_snapshot_20251109T143856Z.csv}"
export SNAPSHOT_PATH
echo "Using SNAPSHOT_PATH=${SNAPSHOT_PATH}"

python -m uvicorn src.api.main:APP --reload --port 8000
