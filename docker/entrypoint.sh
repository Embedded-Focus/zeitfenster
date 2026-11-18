#!/bin/sh
# Run the container command, but back off before exiting when it fails.
#
# podman kube play restarts a failed container with restartPolicy "Always"
# immediately, without the crash-loop backoff a kubelet provides. A process
# that dies at start-up therefore spins the CPU with tight import/start
# cycles (1.2.4 did ~1.7 crashes per second). Sleeping here does not delay
# the restart itself, but every failed iteration idles for the sleep
# duration instead of burning CPU on a doomed start-up.
#
# A clean exit (SIGTERM on pod stop, exit code 0) skips the sleep, so
# deploys stay as fast as before.
set -u

"$@" &
pid=$!
trap 'kill -TERM "$pid" 2>/dev/null; wait "$pid"; exit 0' TERM INT

wait "$pid"
status=$?

if [ "$status" -ne 0 ]; then
    sleep 5
fi
exit "$status"
