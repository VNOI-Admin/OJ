#!/usr/bin/env bash
#
# deploy.sh -- ThinkCode OJ production deploy script (Docker edition)
#
# Runs on the server (14.225.254.134) as the `opencode` user, invoked over
# SSH by .github/workflows/deploy.yml after it merges into the `deploy`
# branch, builds the image on the GitHub Actions runner, and pushes it to
# GHCR. This script does NOT build anything -- it only pulls the already-built
# image and cuts the running services over to it.
#
# Usage: deploy.sh <image-ref>
#   e.g. deploy.sh ghcr.io/hiulaptop/thinkcode-oj:sha-abc1234
#
# High-level flow:
#   1. docker pull the new image
#   2. Run migrations in a throwaway container using the NEW image, against
#      the real production DB (migrations must be safe/backward-compatible
#      with the OLD image still running -- see CI-CD.md).
#   3. Sync the new image's baked-in static assets out to
#      /var/www/thinkcodeoj (nginx serves these directly, not via a
#      container).
#   4. Cut over: docker compose up -d with the new image tag. This recreates
#      site/bridged/celery/wsevent in place (a few seconds of downtime while
#      the port/socket is released and rebound -- see CI-CD.md for why true
#      zero-downtime blue-green isn't possible with a single judge worker
#      pinned to one bridge port).
#   5. Verify:
#      a. site container healthcheck passes (HTTP 200 on 127.0.0.1:8000)
#      b. the judge worker reconnects to bridged and shows online=True in
#         the DB within VERIFY_TIMEOUT seconds (does NOT submit a real test
#         problem -- connection-level check only)
#   6. If verification fails at any point, AUTOMATICALLY roll back to the
#      previously running image tag and re-verify. The old image tag is
#      recorded before step 4 specifically to make this possible.
#
# Exit 0 = deploy succeeded and is live. Exit non-zero = deploy failed;
# either successfully rolled back (site is on the OLD code, still exit
# non-zero so the GitHub Actions job is marked failed and someone looks at
# it) or, in the worst case, rollback itself failed (site may be down --
# see the final error message for manual recovery steps).

set -uo pipefail   # NOT -e: we need to handle failures explicitly to trigger rollback

DEPLOY_DIR="/home/opencode/thinkcode-deploy"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.production.yml"
ENV_FILE="${DEPLOY_DIR}/.env"
STATE_FILE="${DEPLOY_DIR}/current_image.txt"
STATIC_ROOT_HOST="/var/www/thinkcodeoj/static"
PASSTHROUGH_HOST="/var/www/thinkcodeoj/static-passthrough"
ICONS_HOST="/var/www/thinkcodeoj/icons"
DOMAIN="oj.thinkcode.vn"
VERIFY_TIMEOUT=60          # seconds to wait for judge to reconnect + site to answer
                            # (originally bumped to 90 suspecting the judge
                            # needed more time to reconnect after all 4
                            # containers got recreated together -- turned out
                            # the REAL cause of both prior "timeouts" was an
                            # unrelated bug: IMAGE_TAG wasn't exported, so
                            # verify_healthy()'s judge check failed
                            # immediately every time regardless of timeout,
                            # see the `export IMAGE_TAG` comment below. Once
                            # actually fixed, judge reconnect + verification
                            # completes in a few seconds, so reverted back to
                            # 60s.)
VERIFY_POLL_INTERVAL=3

NEW_IMAGE="${1:?Usage: deploy.sh <image-ref>}"

log()  { echo -e "\n\033[1;34m==> $*\033[0m"; }
warn() { echo -e "\033[1;33mWARNING: $*\033[0m" >&2; }
die()  { echo -e "\033[1;31mDEPLOY FAILED: $*\033[0m" >&2; exit 1; }

cd "$DEPLOY_DIR" || die "deploy dir ${DEPLOY_DIR} does not exist -- run initial server setup first"

# ----------------------------------------------------------------------
# Helper: check a) site answers HTTP 200, b) judge worker is online=True
# in the DB. Used both for post-deploy verification and post-rollback
# re-verification.
# ----------------------------------------------------------------------
verify_healthy() {
    local elapsed=0
    local site_ok=false
    local judge_ok=false

    while [ "$elapsed" -lt "$VERIFY_TIMEOUT" ]; do
        if [ "$site_ok" = false ]; then
            code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN}" http://127.0.0.1:8000/ || echo 000)"
            [ "$code" = "200" ] && site_ok=true
        fi

        if [ "$judge_ok" = false ]; then
            # Connection-level check only (per design decision): does NOT
            # submit a real test problem, just checks judge.models.Judge.online.
            result="$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T site \
                python3 manage.py shell -c "
from judge.models import Judge
import sys
online = Judge.objects.filter(online=True).exists()
sys.exit(0 if online else 1)
" 2>/dev/null && echo OK || echo FAIL)"
            [ "$result" = "OK" ] && judge_ok=true
        fi

        if [ "$site_ok" = true ] && [ "$judge_ok" = true ]; then
            echo "Verified: site HTTP 200, judge worker online=True (after ${elapsed}s)"
            return 0
        fi

        sleep "$VERIFY_POLL_INTERVAL"
        elapsed=$((elapsed + VERIFY_POLL_INTERVAL))
    done

    echo "Verification timed out after ${VERIFY_TIMEOUT}s: site_ok=${site_ok} judge_ok=${judge_ok}" >&2
    return 1
}

# ----------------------------------------------------------------------
# 0. Record current state for rollback
# ----------------------------------------------------------------------
PREV_IMAGE=""
if [ -f "$STATE_FILE" ]; then
    PREV_IMAGE="$(cat "$STATE_FILE")"
fi
echo "Previous image: ${PREV_IMAGE:-<none, first deploy>}"
echo "New image:      ${NEW_IMAGE}"

if [ "$PREV_IMAGE" = "$NEW_IMAGE" ]; then
    echo "Already running ${NEW_IMAGE}, nothing to do."
    exit 0
fi

# ----------------------------------------------------------------------
# 1. Pull new image
# ----------------------------------------------------------------------
log "Pulling ${NEW_IMAGE}"
docker pull "$NEW_IMAGE" || die "docker pull failed for ${NEW_IMAGE}"

# ----------------------------------------------------------------------
# 2. Run migrations against the NEW image, BEFORE touching running services.
#    If this fails, nothing running gets touched at all -- old containers
#    keep serving on the old image, old code.
# ----------------------------------------------------------------------
log "Running database migrations (new image, throwaway container)"
docker run --rm \
    --network host \
    --env-file "$ENV_FILE" \
    -v "${DEPLOY_DIR}/local_settings.py:/site/dmoj/local_settings.py:ro" \
    "$NEW_IMAGE" \
    python3 manage.py migrate --noinput \
    || die "migrations failed on ${NEW_IMAGE}. Old services untouched, still running ${PREV_IMAGE:-previous image}."

log "Sanity check (manage.py check) on new image"
docker run --rm \
    --network host \
    --env-file "$ENV_FILE" \
    -v "${DEPLOY_DIR}/local_settings.py:/site/dmoj/local_settings.py:ro" \
    "$NEW_IMAGE" \
    python3 manage.py check \
    || die "manage.py check failed on ${NEW_IMAGE}. Old services untouched, still running ${PREV_IMAGE:-previous image}."

# ----------------------------------------------------------------------
# 3. Sync baked-in static assets out to the host, so nginx (which serves
#    /static directly off disk, not through a container) picks up the new
#    ones. Done BEFORE cutover so there's no window where nginx serves
#    static files that don't match the about-to-be-live code.
# ----------------------------------------------------------------------
log "Syncing static assets to ${STATIC_ROOT_HOST}"
tmp_container="$(docker create "$NEW_IMAGE")"
docker cp "${tmp_container}:/site/static/." "$STATIC_ROOT_HOST/" || { docker rm -f "$tmp_container" >/dev/null; die "failed to copy static assets"; }
mkdir -p "$PASSTHROUGH_HOST" "$ICONS_HOST"
docker cp "${tmp_container}:/site/502.html" "$PASSTHROUGH_HOST/502.html" 2>/dev/null || true
docker cp "${tmp_container}:/site/robots.txt" "$PASSTHROUGH_HOST/robots.txt" 2>/dev/null || true
docker cp "${tmp_container}:/site/resources/icons/." "$ICONS_HOST/" 2>/dev/null || true
docker rm -f "$tmp_container" >/dev/null

# ----------------------------------------------------------------------
# 4. Cut over. NOTE: bridged uses a single fixed port (9999) that the one
#    real judge worker is pinned to in its own judge.yml config -- Docker
#    can't bind the new bridged container to that port until the old one
#    releases it, so there IS a brief gap (typically a few seconds) where
#    no bridge is listening and the judge worker will see its connection
#    drop and retry. This is unavoidable with a single judge worker/single
#    bridge port and is the reason verification happens AFTER cutover
#    (with auto-rollback) rather than before, as originally discussed.
# ----------------------------------------------------------------------
log "Cutting over to ${NEW_IMAGE}"
# IMAGE_TAG must be `export`ed (not just prefixed on this one command) --
# verify_healthy() below also runs `docker compose ... exec`, which parses
# the whole compose file (including the x-image anchor's ${IMAGE_TAG:?...}
# interpolation) even just to exec into an already-running container. A
# real deploy run caught this: verify_healthy()'s judge check silently
# failed every single time with "IMAGE_TAG must be set" (not a judge
# reconnect problem at all), causing spurious rollbacks even though the
# judge worker and site were both actually healthy the whole time.
export IMAGE_TAG="$NEW_IMAGE"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans \
    || die "docker compose up failed. Services may be in a partially-updated state -- check 'docker compose -f ${COMPOSE_FILE} ps' manually."

# ----------------------------------------------------------------------
# 5. Verify: site HTTP 200 + judge worker reconnected (online=True)
# ----------------------------------------------------------------------
log "Verifying new deployment (site HTTP 200 + judge worker online, timeout ${VERIFY_TIMEOUT}s)"
if verify_healthy; then
    echo "$NEW_IMAGE" > "$STATE_FILE"
    echo ""
    echo "=========================================="
    echo " Deploy successful"
    echo " ${PREV_IMAGE:-<none>} -> ${NEW_IMAGE}"
    echo " Site HTTP 200, judge worker online=True"
    echo "=========================================="
    exit 0
fi

# ----------------------------------------------------------------------
# 6. Verification failed -- automatic rollback
# ----------------------------------------------------------------------
warn "Verification failed for ${NEW_IMAGE}."

if [ -z "$PREV_IMAGE" ]; then
    die "No previous image recorded (this was the first deploy) -- cannot auto-rollback. Site may be broken. Manual intervention required: check 'docker compose -f ${COMPOSE_FILE} logs' on the server."
fi

log "Rolling back to ${PREV_IMAGE}"
export IMAGE_TAG="$PREV_IMAGE"   # see the export IMAGE_TAG comment above -- same reason
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans

log "Re-verifying after rollback (timeout ${VERIFY_TIMEOUT}s)"
if verify_healthy; then
    echo "$PREV_IMAGE" > "$STATE_FILE"
    echo ""
    echo "=========================================="
    echo " Deploy FAILED and was automatically rolled back"
    echo " Attempted: ${NEW_IMAGE} (broken -- see logs above)"
    echo " Now running: ${PREV_IMAGE} (confirmed healthy)"
    echo "=========================================="
    exit 1
fi

# Rollback itself failed to verify -- worst case. Site might genuinely be
# down for reasons unrelated to the image (DB down, judge container crashed,
# etc). Do not silently retry forever; surface loudly and stop.
die "Rollback to ${PREV_IMAGE} ALSO failed verification. Site may be down. SSH in and run:
  docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} ps
  docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} logs --tail=100
  sudo docker ps -a --filter name=thinkcode-judge
to diagnose manually."
