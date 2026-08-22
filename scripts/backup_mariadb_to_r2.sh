#!/usr/bin/env bash
set -euo pipefail

: "${DB_NAME:?DB_NAME is required}"
: "${DB_USER:?DB_USER is required}"
: "${DB_PASSWORD:?DB_PASSWORD is required}"
: "${RCLONE_REMOTE:?RCLONE_REMOTE is required, e.g. r2:thinkcode-backups}"

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/thinkcodeoj}"
STAMP="$(date -u +%Y/%m/%d/%H%M%SZ)"
mkdir -p "$BACKUP_ROOT"
WORK_DIR="$(mktemp -d "${BACKUP_ROOT}/.db-${STAMP##*/}.XXXXXX")"
ARCHIVE="${WORK_DIR}/thinkcode-${STAMP//\//-}.sql.gz"

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

export MYSQL_PWD="$DB_PASSWORD"
mariadb-dump \
    --single-transaction \
    --routines \
    --events \
    --triggers \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --user="$DB_USER" \
    "$DB_NAME" | gzip -9 > "$ARCHIVE"
unset MYSQL_PWD

test -s "$ARCHIVE"
rclone copyto "$ARCHIVE" "${RCLONE_REMOTE}/db/${STAMP}.sql.gz" --immutable
echo "Uploaded ${RCLONE_REMOTE}/db/${STAMP}.sql.gz"
