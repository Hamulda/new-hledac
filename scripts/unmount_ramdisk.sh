#!/usr/bin/env bash
#
# unmount_ramdisk.sh — Safely unmount the Hledac RAM disk.
#
# Idempotent: if RAM disk is not mounted, exits 0.
# Requires macOS (hdiutil).
#

set -euo pipefail

MOUNT_POINT="${MOUNT_POINT:-/tmp/hledac_ramdisk}"

log_info()  { echo "[unmount_ramdisk] $*"; }
log_error() { echo "[unmount_ramdisk] ERROR: $*" >&2; }

is_mounted() {
  mount | grep -q "on ${MOUNT_POINT} "
}

main() {
  if ! is_mounted; then
    log_info "RAM disk not mounted at ${MOUNT_POINT} — idempotent exit"
    exit 0
  fi

  log_info "Unmounting RAM disk at ${MOUNT_POINT}..."

  # Find the device associated with the mount point
  DEVICE=$(mount | grep "on ${MOUNT_POINT} " | awk '{print $1}' | head -1 || true)

  if [[ -z "${DEVICE}" ]]; then
    log_error "Could not find device for ${MOUNT_POINT}"
    exit 1
  fi

  # Sync first to flush any pending writes
  sync || true

  # Unmount via hdiutil
  if ! hdiutil detach "${DEVICE}" > /dev/null 2>&1; then
    log_error "hdiutil detach failed for ${DEVICE}"
    exit 1
  fi

  log_info "RAM disk detached: ${DEVICE}"
  exit 0
}

main "$@"
