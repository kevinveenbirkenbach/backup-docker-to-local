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

# Host-side access to the DinD daemon goes through `docker exec` (dind()
# below) instead of a host-published port: port publishing is not reachable
# from every environment (sandboxed runners, hosts with broken loopback
# publishing), while exec only needs the outer docker socket. The TCP
# listener stays for the test container inside the dedicated network.
DIND_HOST_IN_NET="${E2E_DIND_HOST_IN_NET:-tcp://${DIND}:2375}"

dind() { docker exec "${DIND}" docker "$@"; }
dind_stdin() { docker exec -i "${DIND}" docker "$@"; }

IMG="${E2E_IMAGE:-baudolo:local}"
RSYNC_IMG="${E2E_RSYNC_IMAGE:-ghcr.io/kevinveenbirkenbach/alpine-rsync}"

READY_TIMEOUT_SECONDS="${E2E_READY_TIMEOUT_SECONDS:-120}"
ARTIFACTS_DIR="${E2E_ARTIFACTS_DIR:-./artifacts}"

DIND_MTU="${E2E_DIND_MTU:-1280}"

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
    echo "=== DinD reachable? (docker exec ${DIND} docker version) ==="
    dind version || true
    echo
  } > "${ARTIFACTS_DIR}/debug-host-${TS}.txt" 2>&1 || true

  # DinD logs
  docker logs --tail=5000 "${DIND}" > "${ARTIFACTS_DIR}/dind-logs-${TS}.txt" 2>&1 || true

  # DinD state
  {
    echo "=== dind ps -a ==="
    dind ps -a || true
    echo
    echo "=== dind images ==="
    dind images || true
    echo
    echo "=== dind network ls ==="
    dind network ls || true
    echo
    echo "=== dind volume ls ==="
    dind volume ls || true
    echo
    echo "=== dind system df ==="
    dind system df || true
  } > "${ARTIFACTS_DIR}/debug-dind-${TS}.txt" 2>&1 || true

  # Try to capture recent events (best effort; might be noisy)
  dind events --since 10m --until 0s \
    > "${ARTIFACTS_DIR}/dind-events-${TS}.txt" 2>&1 || true

  # The shared tmp volume is mounted at /tmp inside the DinD container
  # itself, so tar it there and copy it out with the outer daemon.
  log "DEBUG: archiving shared /tmp (volume ${E2E_TMP_VOL})"
  docker exec "${DIND}" tar -czf "/tmpdump-${TS}.tar.gz" -C /tmp . >/dev/null 2>&1 || true
  docker cp "${DIND}:/tmpdump-${TS}.tar.gz" "${ARTIFACTS_DIR}/e2e-tmp-${TS}.tar.gz" >/dev/null 2>&1 || true

  log "DEBUG: artifacts written:"
  find "${ARTIFACTS_DIR}" -maxdepth 1 -mindepth 1 -print | sed 's/^/   /' || true
}

cleanup() {
  if [ "${FAILED}" -eq 1 ] && [ "${KEEP_ON_FAIL}" = "1" ]; then
    log "KEEP_ON_FAIL=1 and failure detected -> skipping cleanup."
    log "Next steps:"
    echo "   - Inspect DinD logs: docker logs ${DIND} | less"
    echo "   - Use DinD daemon:  docker exec ${DIND} docker ps -a"
    echo "   - Shared tmp vol:   docker exec ${DIND} ls -la /tmp"
    echo "   - DinD docker root: docker exec ${DIND} ls -la /var/lib/docker/volumes"
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

log "(Re)creating network ${NET} with MTU ${DIND_MTU}"
docker network rm "${NET}" >/dev/null 2>&1 || true
docker network create \
  --opt com.docker.network.driver.mtu="${DIND_MTU}" \
  "${NET}" >/dev/null

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
  docker:dind \
  --host=tcp://0.0.0.0:2375 \
  --tls=false \
  --mtu="${DIND_MTU}" >/dev/null

log "Waiting for DinD to be ready..."
for i in $(seq 1 "${READY_TIMEOUT_SECONDS}"); do
  if dind version >/dev/null 2>&1; then
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
dind pull "${RSYNC_IMG}"

log "Ensuring alpine exists in DinD (for debug helpers)"
dind pull alpine:3.20 >/dev/null

log "Loading ${IMG} image into DinD..."
docker save "${IMG}" | dind_stdin load >/dev/null

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
