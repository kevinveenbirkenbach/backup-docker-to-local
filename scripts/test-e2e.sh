#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# E2E runner using Docker-in-Docker (DinD) with debug-on-failure
#
# Debug toggles:
#   E2E_KEEP_ON_FAIL=1   -> keep DinD + volumes + network if tests fail
#   E2E_KEEP_VOLUMES=1   -> keep volumes even on success/cleanup
#   E2E_DEBUG_SHELL=1    -> open an interactive shell in the test container instead of running tests
#   E2E_ARTIFACTS_DIR=./artifacts
# -----------------------------------------------------------------------------

NET="${E2E_NET:-baudolo-e2e-net}"
DIND="${E2E_DIND_NAME:-baudolo-e2e-dind}"
DIND_VOL="${E2E_DIND_VOL:-baudolo-e2e-dind-data}"
E2E_TMP_VOL="${E2E_TMP_VOL:-baudolo-e2e-tmp}"

DIND_HOST="${E2E_DIND_HOST:-tcp://127.0.0.1:2375}"
DIND_HOST_IN_NET="${E2E_DIND_HOST_IN_NET:-tcp://${DIND}:2375}"

IMG="${E2E_IMAGE:-baudolo:local}"
RSYNC_IMG="${E2E_RSYNC_IMAGE:-ghcr.io/kevinveenbirkenbach/alpine-rsync}"

READY_TIMEOUT_SECONDS="${E2E_READY_TIMEOUT_SECONDS:-120}"
ARTIFACTS_DIR="${E2E_ARTIFACTS_DIR:-./artifacts}"

KEEP_ON_FAIL="${E2E_KEEP_ON_FAIL:-0}"
KEEP_VOLUMES="${E2E_KEEP_VOLUMES:-0}"
DEBUG_SHELL="${E2E_DEBUG_SHELL:-0}"

FAILED=0
TS="$(date +%Y%m%d%H%M%S)"

mkdir -p "${ARTIFACTS_DIR}"

log() { echo ">> $*"; }

dump_debug() {
  log "DEBUG: collecting diagnostics into ${ARTIFACTS_DIR}"

  {
    echo "=== Host docker version ==="
    docker version || true
    echo
    echo "=== Host docker info ==="
    docker info || true
    echo
    echo "=== DinD reachable? (docker -H ${DIND_HOST} version) ==="
    docker -H "${DIND_HOST}" version || true
    echo
  } > "${ARTIFACTS_DIR}/debug-host-${TS}.txt" 2>&1 || true

  # DinD logs
  docker logs --tail=5000 "${DIND}" > "${ARTIFACTS_DIR}/dind-logs-${TS}.txt" 2>&1 || true

  # DinD state
  {
    echo "=== docker -H ps -a ==="
    docker -H "${DIND_HOST}" ps -a || true
    echo
    echo "=== docker -H images ==="
    docker -H "${DIND_HOST}" images || true
    echo
    echo "=== docker -H network ls ==="
    docker -H "${DIND_HOST}" network ls || true
    echo
    echo "=== docker -H volume ls ==="
    docker -H "${DIND_HOST}" volume ls || true
    echo
    echo "=== docker -H system df ==="
    docker -H "${DIND_HOST}" system df || true
  } > "${ARTIFACTS_DIR}/debug-dind-${TS}.txt" 2>&1 || true

  # Try to capture recent events (best effort; might be noisy)
  docker -H "${DIND_HOST}" events --since 10m --until 0s \
    > "${ARTIFACTS_DIR}/dind-events-${TS}.txt" 2>&1 || true

  # Dump shared /tmp content from the tmp volume:
  # We create a temporary container that mounts the volume, then tar its content.
  # (Does not rely on host filesystem paths.)
  log "DEBUG: archiving shared /tmp (volume ${E2E_TMP_VOL})"
  docker -H "${DIND_HOST}" run --rm \
    -v "${E2E_TMP_VOL}:/tmp" \
    alpine:3.20 \
    bash -lc 'cd /tmp && tar -czf /out.tar.gz . || true' \
    >/dev/null 2>&1 || true

  # The above writes inside the container FS, not to host. So do it properly:
  # Use "docker cp" from a temp container.
  local tmpc="baudolo-e2e-tmpdump-${TS}"
  docker -H "${DIND_HOST}" rm -f "${tmpc}" >/dev/null 2>&1 || true
  docker -H "${DIND_HOST}" create --name "${tmpc}" -v "${E2E_TMP_VOL}:/tmp" alpine:3.20 \
    bash -lc 'cd /tmp && tar -czf /tmpdump.tar.gz . || true' >/dev/null
  docker -H "${DIND_HOST}" start -a "${tmpc}" >/dev/null 2>&1 || true
  docker -H "${DIND_HOST}" cp "${tmpc}:/tmpdump.tar.gz" "${ARTIFACTS_DIR}/e2e-tmp-${TS}.tar.gz" >/dev/null 2>&1 || true
  docker -H "${DIND_HOST}" rm -f "${tmpc}" >/dev/null 2>&1 || true

  log "DEBUG: artifacts written:"
  ls -la "${ARTIFACTS_DIR}" | sed 's/^/   /' || true
}

cleanup() {
  if [ "${FAILED}" -eq 1 ] && [ "${KEEP_ON_FAIL}" = "1" ]; then
    log "KEEP_ON_FAIL=1 and failure detected -> skipping cleanup."
    log "Next steps:"
    echo "   - Inspect DinD logs: docker logs ${DIND} | less"
    echo "   - Use DinD daemon:  docker -H ${DIND_HOST} ps -a"
    echo "   - Shared tmp vol:   docker -H ${DIND_HOST} run --rm -v ${E2E_TMP_VOL}:/tmp alpine:3.20 ls -la /tmp"
    echo "   - DinD docker root: docker -H ${DIND_HOST} run --rm -v ${DIND_VOL}:/var/lib/docker alpine:3.20 ls -la /var/lib/docker/volumes"
    return 0
  fi

  log "Cleanup: stopping ${DIND} and removing network ${NET}"
  docker rm -f "${DIND}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true

  if [ "${KEEP_VOLUMES}" != "1" ]; then
    docker volume rm -f "${DIND_VOL}" >/dev/null 2>&1 || true
    docker volume rm -f "${E2E_TMP_VOL}" >/dev/null 2>&1 || true
  else
    log "Keeping volumes (E2E_KEEP_VOLUMES=1): ${DIND_VOL}, ${E2E_TMP_VOL}"
  fi
}
trap cleanup EXIT INT TERM

log "Creating network ${NET} (if missing)"
docker network inspect "${NET}" >/dev/null 2>&1 || docker network create "${NET}" >/dev/null

log "Removing old ${DIND} (if any)"
docker rm -f "${DIND}" >/dev/null 2>&1 || true

log "(Re)creating DinD data volume ${DIND_VOL}"
docker volume rm -f "${DIND_VOL}" >/dev/null 2>&1 || true
docker volume create "${DIND_VOL}" >/dev/null

log "(Re)creating shared /tmp volume ${E2E_TMP_VOL}"
docker volume rm -f "${E2E_TMP_VOL}" >/dev/null 2>&1 || true
docker volume create "${E2E_TMP_VOL}" >/dev/null

log "Starting Docker-in-Docker daemon ${DIND}"
docker run -d --privileged \
  --name "${DIND}" \
  --network "${NET}" \
  -e DOCKER_TLS_CERTDIR="" \
  -v "${DIND_VOL}:/var/lib/docker" \
  -v "${E2E_TMP_VOL}:/tmp" \
  -p 2375:2375 \
  docker:dind \
  --host=tcp://0.0.0.0:2375 \
  --tls=false >/dev/null

log "Waiting for DinD to be ready..."
for i in $(seq 1 "${READY_TIMEOUT_SECONDS}"); do
  if docker -H "${DIND_HOST}" version >/dev/null 2>&1; then
    log "DinD is ready."
    break
  fi
  sleep 1
  if [ "${i}" -eq "${READY_TIMEOUT_SECONDS}" ]; then
    echo "ERROR: DinD did not become ready in time"
    docker logs --tail=200 "${DIND}" || true
    FAILED=1
    dump_debug || true
    exit 1
  fi
done

log "Pre-pulling helper images in DinD..."
log " - Pulling: ${RSYNC_IMG}"
docker -H "${DIND_HOST}" pull "${RSYNC_IMG}"

log "Ensuring alpine exists in DinD (for debug helpers)"
docker -H "${DIND_HOST}" pull alpine:3.20 >/dev/null

log "Loading ${IMG} image into DinD..."
docker save "${IMG}" | docker -H "${DIND_HOST}" load >/dev/null

log "Running E2E tests inside DinD"
set +e
if [ "${DEBUG_SHELL}" = "1" ]; then
  log "E2E_DEBUG_SHELL=1 -> opening shell in test container"
  docker run --rm -it \
    --network "${NET}" \
    -e DOCKER_HOST="${DIND_HOST_IN_NET}" \
    -e E2E_RSYNC_IMAGE="${RSYNC_IMG}" \
    -v "${DIND_VOL}:/var/lib/docker:ro" \
    -v "${E2E_TMP_VOL}:/tmp" \
    "${IMG}" \
    bash -lc '
      set -e
      if [ ! -f /etc/machine-id ]; then
        mkdir -p /etc
        cat /proc/sys/kernel/random/uuid > /etc/machine-id
      fi
      echo ">> DOCKER_HOST=${DOCKER_HOST}"
      docker ps -a || true
      exec bash
    '
  rc=$?
else
  docker run --rm \
    --network "${NET}" \
    -e DOCKER_HOST="${DIND_HOST_IN_NET}" \
    -e E2E_RSYNC_IMAGE="${RSYNC_IMG}" \
    -v "${DIND_VOL}:/var/lib/docker:ro" \
    -v "${E2E_TMP_VOL}:/tmp" \
    "${IMG}" \
    bash -lc '
    set -euo pipefail
    set -x
    export PYTHONUNBUFFERED=1

    export TMPDIR=/tmp TMP=/tmp TEMP=/tmp

    if [ ! -f /etc/machine-id ]; then
        mkdir -p /etc
        cat /proc/sys/kernel/random/uuid > /etc/machine-id
    fi

    python -m unittest discover -t . -s tests/e2e -p "test_*.py" -v -f
    '
  rc=$?
fi
set -e

if [ "${rc}" -ne 0 ]; then
  FAILED=1
  echo "ERROR: E2E tests failed (exit code: ${rc})"
  dump_debug || true
  exit "${rc}"
fi

log "E2E tests passed."
