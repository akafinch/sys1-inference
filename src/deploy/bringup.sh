#!/usr/bin/env bash
# Bring the demo up on the GPU host: the weights, OpenJev's three containers and the app's, then
# one question to each model. sys1-bringup.service runs this on every boot after the first, with
# /etc/sys1.env in its environment, and appends its output to /var/log/cloud-init-output.log, the
# log Terraform's bringup_command follows. To run it again: systemctl restart sys1-bringup
#
# Each phase prints "<UTC time> sys1: <phase>", so the log times the bring-up, and a failure
# names the phase it stopped in. ASSUMPTION (unverified): the whole bring-up, first boot included,
# takes tens of minutes; these timestamps are its first measurement.
set -euo pipefail

: "${APP_PORT:?not set: run this as sys1-bringup.service, which reads /etc/sys1.env}"
: "${OPENJEV_VERSION:?not set}" "${DIFFUSIONGEMMA_MODEL:?not set}" "${DIFFUSIONGEMMA_REVISION:?not set}"
: "${LAYA_MODEL:?not set}" "${LAYA_REVISION:?not set}"

deploy=$(dirname "$(readlink -f "$0")")
# Every compose call reads the settings file, as compose.yaml requires.
compose() { docker compose --env-file /etc/sys1.env -f "$deploy/compose.yaml" "$@"; }

phase=start
say() { echo "$(date -u +%FT%TZ) sys1: $*"; }
begin() { phase=$1; say "$1: $2"; }
trap 'status=$?; ((status == 0)) || say "bring-up FAILED (exit $status) in phase $phase; the error is above. Retry: systemctl restart sys1-bringup"' EXIT

# Download one checkpoint at its pinned revision into /opt/models/<name>, unless an earlier boot
# finished it [hf download: https://huggingface.co/docs/huggingface_hub/guides/cli, as-of 2026-10-02].
# hf runs from the openjev-laya image, which ships it; the openjev image's entrypoint ignores its
# arguments and starts vLLM (docker/entrypoint.sh in OpenJev 0.5.1).
fetch() {
  local name=$1 repo=$2 revision=$3
  local marker=/opt/models/$name.revision
  if [[ -f $marker && $(<"$marker") == "$revision" ]]; then
    say "weights: $repo is already in /opt/models/$name at $revision"
    return
  fi
  say "weights: $repo at $revision, into /opt/models/$name"
  docker run --rm -v /opt/models:/models "razorback16/openjev-laya:$OPENJEV_VERSION" \
    hf download "$repo" --revision "$revision" --local-dir "/models/$name"
  echo "$revision" >"$marker" # last, so an interrupted download starts again on the next run
}

# The decision a reply holds, on one line: the question, its top answer, and the two times the
# app reports, OpenJev's own (openjev_ms) and the app's round trip to OpenJev (backend_ms).
# shellcheck disable=SC2016 # the $names are jq's variables, not the shell's
summary='
  .openjev as $reply | ($reply.answers | to_entries[0]) as $question | $question.value as $answer
  | (if $answer.type == "noul" then "noul \($answer.noul)"
     else ($answer.probabilities | to_entries | max_by(.value)) as $top
       | "\($answer.legend[$top.key] // $top.key) (p=\($top.value))"
     end) as $verdict
  | "\($target) [\($reply.model)] \($question.key) -> \($verdict); openjev_ms=\(.openjev_ms) backend_ms=\(.backend_ms)"'

# Ask one target, through the app, the first preset written for it; Laya on the CPU answers a
# Laya preset, the same question Laya on the GPU answers.
decide() {
  local target=$1 written_for=$1 request reply status
  if [[ $target == laya-cpu ]]; then written_for=laya-gpu; fi
  request=$(jq -c --arg target "$target" --arg written_for "$written_for" '
    first(.texts[] as $text | $text.presets[] | select(.target == $written_for)
      | {target: $target, body: {questions: {(.id): .question}, state: $text.state}})' <<<"$catalogue")
  reply=$(curl -sS --max-time 120 -w '\n%{http_code}' -H 'content-type: application/json' \
    -d "$request" "$app/api/ask")
  status=${reply##*$'\n'}
  reply=${reply%$'\n'*}
  if [[ $status != 200 ]]; then
    # the app's own reason (OpenJev unreachable), or OpenJev's
    say "decision: $target answered HTTP $status: $(jq -c '.error // .openjev' <<<"$reply" 2>/dev/null || echo "$reply")"
    return 1
  fi
  say "decision: $(jq -r --arg target "$target" "$summary" <<<"$reply")"
}

say "bring-up begins"
begin driver "does the NVIDIA driver see the GPU?"
if ! gpus=$(nvidia-smi -L 2>&1) || [[ $gpus != GPU* ]]; then
  say "no GPU: nvidia-smi -L says: ${gpus:-nothing}"
  exit 1
fi
echo "$gpus"

begin images "pull OpenJev's two images, unless they are already here"
compose pull --policy missing --ignore-buildable

begin weights "both checkpoints, pinned by revision, into /opt/models"
mkdir -p /opt/models
fetch dgemma "$DIFFUSIONGEMMA_MODEL" "$DIFFUSIONGEMMA_REVISION"
fetch laya "$LAYA_MODEL" "$LAYA_REVISION"

begin stack "build the app's image if needed, start the four containers, wait until each is healthy"
say "the first start loads 19 GB of weights and compiles GPU kernels for some minutes; docker logs -f sys1-openjev-1 shows it"
# --wait has no time limit, as --wait-timeout defaults to 0
# [https://docs.docker.com/reference/cli/docker/compose/up/], and it ends at once, failing, if a
# container it waits for turns unhealthy or exits (pkg/compose/service_containers.go in Compose
# v5.5.1, https://github.com/docker/compose).
compose up -d --wait
compose ps

begin decisions "one question to each model and device, through the app"
app=http://127.0.0.1:$APP_PORT
# The app may still be binding its port, so the first request retries for up to a minute.
catalogue=$(curl -fsS --retry 30 --retry-delay 2 --retry-all-errors "$app/api/presets")
for target in diffusiongemma laya-gpu laya-cpu; do
  decide "$target"
done

phase=ready
say "ready: the page answers on port $APP_PORT"
