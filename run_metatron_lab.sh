#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-}"
ENVFILE="clawtron.env"

#region Load environment variables
if [ -f "$ENVFILE" ]; then
    source "$ENVFILE"
else
    echo "$ENVFILE does not exist."
    exit 1
fi
#endregion

#region Validate target
if [[ -z "$TARGET" ]]; then
  echo "Usage: run_metatron_lab.sh <lab-target-ip>"
  exit 1
fi

case "$TARGET" in
  192.168.56.*|10.0.2.*|172.16.1.*)
    ;;
  *)
    echo "[REFUSED] Target outside approved lab subnet: $TARGET"
    exit 2
    ;;
esac
#endregion

#region Setup output directory
RUN_ID="$(date +%Y%m%d_%H%M%S)_${TARGET}"
OUTDIR="${OUTDIR:-/opt/clawtron/logs}/${RUN_ID}"
mkdir -p "$OUTDIR"

echo "[*] Authorized lab target: $TARGET"
echo "[*] Output directory: $OUTDIR"

{
  echo "run_id=$RUN_ID"
  echo "target=$TARGET"
  echo "started_at=$(date -Is)"
  echo "host=$(hostname)"
  echo "user=$(whoami)"
} > "$OUTDIR/metadata.txt"

if [ -z "$METATRON_PATH" ]; then
    echo "METATRON_PATH is not set in clawtron.env"
    exit 1
fi

if [ ! -d "$METATRON_PATH" ]; then
    echo "METATRON_PATH does not exist: $METATRON_PATH"
    exit 1
fi

VENV_ACTIVATE="$METATRON_PATH/venv/bin/activate"

if [[ ! -f "$VENV_ACTIVATE" ]]; then
    echo "Virtual environment activation script not found: $VENV_ACTIVATE"
    exit 1
fi

if source "$VENV_ACTIVATE"; then
    echo "Activated virtual environment at $METATRON_PATH/venv"
else
    echo "Failed to activate virtual environment at $METATRON_PATH/venv"
    exit 1
fi
#endregion

#region Run Metatron
cd "$METATRON_PATH"

python3 metatron.py "$TARGET" 2>&1 | tee "$OUTDIR/metatron_console.log"

echo "finished_at=$(date -Is)" >> "$OUTDIR/metadata.txt"
echo "[*] Done. Results saved to $OUTDIR"
#endregion