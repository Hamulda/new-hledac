#!/usr/bin/env bash
#
# mount_ramdisk.sh — Create a macOS RAM disk for Hledac scratch space.
#
# Idempotent: if RAM disk already exists, just prepare subdirectories.
# Requires macOS (hdiutil, diskutil).
#
# RAM disk size: 1 GB (2097152 sectors × 512 bytes)
# Mount point: /tmp/hledac_ramdisk
#

set -euo pipefail

MOUNT_POINT="${MOUNT_POINT:-/tmp/hledac_ramdisk}"
SECTOR_SIZE=512
SECTOR_COUNT=2097152  # 1 GB
DEVICE=""

# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

log_info()  { echo "[mount_ramdisk] $*"; }
log_warn()  { echo "[mount_ramdisk] WARNING: $*" >&2; }
log_error() { echo "[mount_ramdisk] ERROR: $*" >&2; }

is_mounted() {
  mount | grep -q "on ${MOUNT_POINT} "
}

# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

main() {
  log_info "Starting RAM disk bootstrap (MOUNT_POINT=${MOUNT_POINT})"

  # Detect if already mounted
  if is_mounted; then
    log_info "RAM disk already mounted at ${MOUNT_POINT}"
    prepare_subdirs
    log_info "Idempotent check complete"
    exit 0
  fi

  # Check for existing device node (orphan from previous run)
  existing=$(mount | grep -E "^/dev/disk[0-9]+ on ${MOUNT_POINT} " | awk '{print $1}' || true)
  if [[ -n "${existing}" ]]; then
    log_info "RAM disk already mounted (detected via mount output): ${existing}"
    exit 0
  fi

  # ----------------------------------------------------------------
  # Zombie Sweep: find and detach orphaned ghost/ramdisk devices
  # ----------------------------------------------------------------
  log_info "Running zombie sweep..."
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    DEVICE_TO_DETACH=$(echo "${line}" | awk '{print $1}')
    log_info "Detaching orphaned device: ${DEVICE_TO_DETACH}"
    hdiutil detach "${DEVICE_TO_DETACH}" > /dev/null 2>&1 || true
  done < <(hdiutil info -plist 2>/dev/null | \
    plutil -extract ImageData xml1 -o - -- - 2>/dev/null | \
    grep -E "/dev/disk[0-9]+" || true)
  log_info "Zombie sweep complete"

  # Create RAM disk device
  log_info "Creating RAM disk device (1 GB)..."
  DEVICE=$(hdiutil attach -nomount ram://${SECTOR_COUNT} 2>&1) || {
    log_error "hdiutil attach failed: ${DEVICE}"
    exit 1
  }
  DEVICE=$(echo "${DEVICE}" | tr -d '[:space:]')
  log_info "Device node: ${DEVICE}"

  # Format as HFS+
  log_info "Formatting as HFS+..."
  diskutil erasevolume HFS+ "RAMDisk" "${DEVICE}" > /dev/null 2>&1 || {
    # Fallback: try exfat for broader compatibility
    log_warn "HFS+ erase failed, trying exfat..."
    diskutil erasevolume ExFAT "RAMDisk" "${DEVICE}" > /dev/null 2>&1 || {
      log_error "diskutil erasevolume failed"
      exit 1
    }
  }

  # Re-detect mount point (erasevolume auto-mounts)
  ACTUAL_MOUNT=$(mount | grep "on /dev/disk[0-9]+ " | awk '{print $3}' | head -1 || true)
  if [[ -z "${ACTUAL_MOUNT}" ]]; then
    log_error "Could not detect RAM disk mount point after erasevolume"
    exit 1
  fi
  MOUNT_POINT="${ACTUAL_MOUNT}"
  log_info "Mounted at: ${MOUNT_POINT}"

  # Prepare subdirectories
  prepare_subdirs

  log_info "RAM disk ready at ${MOUNT_POINT}"
  echo "${MOUNT_POINT}"
}

prepare_subdirs() {
  local dirs=(duckdb_tmp sockets warc arrow)
  for d in "${dirs[@]}"; do
    local target="${MOUNT_POINT}/${d}"
    if [[ ! -d "${target}" ]]; then
      mkdir -p "${target}" || log_warn "Could not create ${target}"
    fi
    # Clear tmp content
    if [[ "${d}" == "duckdb_tmp" ]] || [[ "${d}" == "warc" ]]; then
      rm -rf "${target:?}/"* 2>/dev/null || true
    fi
  done
}

main "$@"
