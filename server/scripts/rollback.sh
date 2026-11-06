#!/usr/bin/env bash
# Restore exactly the backup produced by apply_patch.sh. Does NOT change .env/secrets.
set -euo pipefail
if [[ "$#" -ne 2 ]]; then
  echo "Usage: bash scripts/rollback.sh TARGET_REPO BACKUP_TAR" >&2
  exit 2
fi
TARGET="$(cd "$1" && pwd)"
ARCHIVE="$(realpath "$2")"
[[ -f "$ARCHIVE" ]] || { echo "Missing archive: $ARCHIVE" >&2; exit 2; }
for item in backend/app/main.py backend/tests/test_api.py backend/Dockerfile backend/requirements.txt frontend/nginx.conf compose.yaml; do
  tar -tzf "$ARCHIVE" | grep -qx "$item" || { echo "Backup missing $item" >&2; exit 2; }
done
# This rollback should only be used if no subsequent changes were made to these files.
tar -xzf "$ARCHIVE" -C "$TARGET"
rm -rf "$TARGET/backend/camera_v1" "$TARGET/backend/tests/test_camera_integration.py"
rm -f "$TARGET/contract/camera-v1.openapi.yaml" "$TARGET/contract/ws-control.schema.json" "$TARGET/docs/CAMERA_PROTOCOL_V1.md"
rm -rf "$TARGET/simulator" "$TARGET/tools"
echo "Source files rolled back. The .env file was left untouched."
echo "To apply rollback to containers: cd '$TARGET' && docker compose up -d --build backend frontend"
