#!/usr/bin/env bash
# Rebuild Tier 1 from all verified data: public crops + in-app corrections.
# Usage: bash scripts/retrain.sh <corrections.json> <evidence dir> <crops dir>
set -euo pipefail
node --import tsx tools/corrections_to_crops.ts "$1" "$2" "$3"
python scripts/train_tier1.py --crops "$3" --out apps/web/public/models
node tools/gen_eval_md.mjs
