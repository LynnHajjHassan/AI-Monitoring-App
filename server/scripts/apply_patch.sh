#!/usr/bin/env bash
# SceneSense Phase 3: check snapshot compatibility, back up, then install additive gateway.
set -euo pipefail
PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-$HOME/comp4990-integration-starter}"
TARGET="$(cd "$TARGET" && pwd)"

if [[ ! -d "$TARGET/backend/app" || ! -f "$TARGET/compose.yaml" ]]; then
  echo "ERROR: Target does not look like COMP4990 repository: $TARGET" >&2
  exit 1
fi

# Fail closed rather than overwrite files that have changed since the user's backup.
while read -r expected rel; do
  [[ -f "$TARGET/$rel" ]] || { echo "Missing: $TARGET/$rel" >&2; exit 1; }
  actual="$(sha256sum "$TARGET/$rel" | cut -d' ' -f1)"
  if [[ "$actual" != "$expected" ]]; then
    echo "STOP: $rel differs from the Nov 6 backup snapshot. Merge this file manually; no files have been changed." >&2
    exit 2
  fi
done < "$PATCH_DIR/scripts/expected_base.sha256"

for newpath in backend/camera_v1 backend/tests/test_camera_integration.py docs/CAMERA_PROTOCOL_V1.md contract/camera-v1.openapi.yaml contract/ws-control.schema.json simulator tools; do
  if [[ -e "$TARGET/$newpath" ]]; then
    echo "STOP: $newpath already exists. Review changes before applying; nothing changed." >&2
    exit 2
  fi
done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$HOME/comp4990-backups/phase3-$STAMP"
mkdir -p "$BACKUP_DIR"
chmod 700 "$HOME/comp4990-backups" "$BACKUP_DIR"
(
  cd "$TARGET"
  tar -czf "$BACKUP_DIR/pre-phase3-files.tar.gz" \
    backend/app/main.py backend/tests/test_api.py backend/Dockerfile backend/requirements.txt frontend/nginx.conf compose.yaml
)
chmod 600 "$BACKUP_DIR/pre-phase3-files.tar.gz"

while read -r expected rel; do
  install -m 644 "$PATCH_DIR/$rel" "$TARGET/$rel"
done < "$PATCH_DIR/scripts/expected_base.sha256"
cp -a "$PATCH_DIR/backend/camera_v1" "$TARGET/backend/camera_v1"
cp -a "$PATCH_DIR/backend/tests/test_camera_integration.py" "$TARGET/backend/tests/test_camera_integration.py"
mkdir -p "$TARGET/contract" "$TARGET/docs"
cp -a "$PATCH_DIR/contract/camera-v1.openapi.yaml" "$TARGET/contract/camera-v1.openapi.yaml"
cp -a "$PATCH_DIR/contract/ws-control.schema.json" "$TARGET/contract/ws-control.schema.json"
cp -a "$PATCH_DIR/docs/CAMERA_PROTOCOL_V1.md" "$TARGET/docs/CAMERA_PROTOCOL_V1.md"
cp -a "$PATCH_DIR/simulator" "$TARGET/simulator"
cp -a "$PATCH_DIR/tools" "$TARGET/tools"

echo "Files installed successfully in $TARGET"
echo "Pre-change backup: $BACKUP_DIR/pre-phase3-files.tar.gz"
echo "Next: generate camera tokens, run pytest, then docker compose up -d --build backend frontend."
echo "No Docker containers were restarted by this script."
