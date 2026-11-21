#!/usr/bin/env bash
# =============================================================================
# controlled_burst_experiment.sh
#
# Gap 4 fix: Controlled burst experiment that measures onset-to-Ready latency
# for both reactive HPA and predictive HPA under identical conditions.
#
# Protocol
# --------
#   1. Reset StatefulSet to MIN_REPLICAS (confirms headroom exists).
#   2. Wait for cluster to stabilise (PSI < 0.5 % for 60 s).
#   3. Inject a repeatable fio I/O burst (same workload every run).
#   4. Record four timestamps per run:
#        T_onset   – moment fio starts (Unix epoch, ms)
#        T_psi     – first sample where PSI avg10 >= 1.80 %
#        T_hpa     – first HPA scale-up decision (kubectl events)
#        T_ready   – first new pod reaches Ready state
#   5. Compute:
#        t_detect  = T_psi  - T_onset   (seconds PSI takes to cross threshold)
#        t_hpa     = T_hpa  - T_onset   (seconds until HPA decides to scale)
#        t_ready   = T_ready - T_onset  (onset-to-Ready end-to-end latency)
#   6. Run N_RUNS repetitions; alternate REACTIVE / PREDICTIVE each run.
#   7. Write every measurement to results/burst_experiment_<timestamp>.csv
#      and print a summary table.
#
# Usage
# -----
#   # Run both modes (default 5 runs per mode):
#   ./controlled_burst_experiment.sh
#
#   # Run reactive-only, 10 runs:
#   MODE=reactive N_RUNS=10 ./controlled_burst_experiment.sh
#
#   # Run predictive-only:
#   MODE=predictive N_RUNS=5 ./controlled_burst_experiment.sh
#
# Requirements
# ------------
#   kubectl, fio (or stress-ng fallback), jq, bc
#   Kind cluster running with prometheus-stack and workload-app StatefulSet.
#   For predictive mode: prediction service must be running and
#   predicted_psi_confirmed must appear in the custom metrics API.
#
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
NAMESPACE="${NAMESPACE:-default}"
STATEFULSET="${STATEFULSET:-workload-app}"
MIN_REPLICAS="${MIN_REPLICAS:-2}"
MAX_REPLICAS="${MAX_REPLICAS:-8}"
N_RUNS="${N_RUNS:-5}"              # runs per mode
MODE="${MODE:-both}"               # reactive | predictive | both
BURST_DURATION_S="${BURST_DURATION_S:-120}"  # seconds of I/O load
SETTLE_TIMEOUT_S="${SETTLE_TIMEOUT_S:-300}"  # max wait for PSI to drop
PSI_THRESHOLD="${PSI_THRESHOLD:-1.80}"
PSI_METRIC_QUERY='avg(container_pressure_io_some_avg10{pod=~"workload-app-.*",container!=""})'
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
RESULTS_DIR="${RESULTS_DIR:-$(dirname "$0")/../../results/burst_experiment}"
LOG_PREFIX="burst_$(date +%Y%m%d_%H%M%S)"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR]${NC}   $*"; }
hdr()   { echo -e "\n${BOLD}$*${NC}"; echo "$(printf '=%.0s' {1..72})"; }

# ── Helpers ───────────────────────────────────────────────────────────────────
now_ms() { date +%s%3N; }   # Unix epoch in milliseconds
now_s()  { date +%s; }

query_psi() {
    # Return current avg PSI as a float (empty string on failure).
    local result
    result=$(curl -sf "${PROMETHEUS_URL}/api/v1/query" \
        --data-urlencode "query=${PSI_METRIC_QUERY}" 2>/dev/null \
        | jq -r '.data.result[0].value[1] // empty' 2>/dev/null) || true
    echo "${result:-}"
}

wait_for_psi_below() {
    # Wait until PSI drops below $1 (%) for at least $2 consecutive seconds.
    local target="$1" stable_s="${2:-30}"
    local stable_count=0 elapsed=0
    info "Waiting for PSI < ${target}% (stable for ${stable_s}s) …"
    while (( elapsed < SETTLE_TIMEOUT_S )); do
        local psi; psi=$(query_psi)
        if [[ -n "$psi" ]] && (( $(echo "$psi < $target" | bc -l) )); then
            (( stable_count += 5 ))
            (( stable_count >= stable_s )) && { ok "PSI settled at ${psi}%"; return 0; }
        else
            stable_count=0
        fi
        sleep 5
        (( elapsed += 5 ))
    done
    warn "PSI did not settle below ${target}% within ${SETTLE_TIMEOUT_S}s (last=${psi:-?})"
    return 1
}

reset_to_min_replicas() {
    info "Scaling ${STATEFULSET} down to ${MIN_REPLICAS} replicas …"
    kubectl scale statefulset "${STATEFULSET}" -n "${NAMESPACE}" \
        --replicas="${MIN_REPLICAS}"
    # Wait until exactly MIN_REPLICAS pods are Ready
    kubectl rollout status statefulset/"${STATEFULSET}" -n "${NAMESPACE}" \
        --timeout=120s
    local actual
    actual=$(kubectl get statefulset "${STATEFULSET}" -n "${NAMESPACE}" \
        -o jsonpath='{.status.readyReplicas}')
    ok "StatefulSet at ${actual}/${MIN_REPLICAS} ready replicas"
    if (( actual > MIN_REPLICAS )); then
        err "More replicas than expected — aborting to avoid a pre-saturated run"
        exit 1
    fi
}

apply_hpa() {
    local mode="$1"
    if [[ "$mode" == "reactive" ]]; then
        kubectl apply -f "$(dirname "$0")/workload-reactive-hpa.yaml" -n "${NAMESPACE}" >/dev/null
        kubectl delete hpa workload-predictive-hpa -n "${NAMESPACE}" --ignore-not-found >/dev/null
        info "Reactive HPA active"
    else
        kubectl apply -f "$(dirname "$0")/workload-predictive-hpa.yaml" -n "${NAMESPACE}" >/dev/null
        kubectl delete hpa workload-reactive-hpa -n "${NAMESPACE}" --ignore-not-found >/dev/null
        info "Predictive HPA active"
    fi
    sleep 5   # let the HPA controller pick up the new object
}

inject_io_burst() {
    # Launch fio inside a workload pod to generate repeatable I/O pressure.
    # Falls back to stress-ng --io if fio is unavailable.
    local pod
    pod=$(kubectl get pods -n "${NAMESPACE}" -l app=workload \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -z "$pod" ]]; then err "No workload pod found"; return 1; fi

    info "Injecting I/O burst in pod ${pod} for ${BURST_DURATION_S}s …"

    # Try fio first (more repeatable I/O pattern)
    if kubectl exec -n "${NAMESPACE}" "${pod}" -- which fio &>/dev/null; then
        kubectl exec -n "${NAMESPACE}" "${pod}" -- \
            fio --name=presync-burst \
                --rw=randrw \
                --bs=4k \
                --iodepth=32 \
                --numjobs=4 \
                --size=512m \
                --runtime="${BURST_DURATION_S}" \
                --time_based \
                --group_reporting \
                --filename=/tmp/presync_fio_test \
                --direct=1 \
                --output=/dev/null &
    else
        # Fallback: stress-ng I/O workers
        kubectl exec -n "${NAMESPACE}" "${pod}" -- \
            stress-ng --io 4 --hdd 2 --timeout "${BURST_DURATION_S}s" \
                      --metrics-brief &>/dev/null &
    fi
}

wait_for_psi_spike() {
    # Poll PSI every 5 s until it crosses SPIKE_THRESHOLD or timeout.
    # Returns the timestamp (ms) when PSI first exceeded the threshold.
    local deadline=$(( $(now_s) + 180 ))   # 3-minute window
    while (( $(now_s) < deadline )); do
        local psi; psi=$(query_psi)
        if [[ -n "$psi" ]] && (( $(echo "$psi >= $PSI_THRESHOLD" | bc -l) )); then
            echo "$(now_ms)"
            return 0
        fi
        sleep 5
    done
    echo ""   # empty = no spike detected
}

wait_for_hpa_scaleup() {
    # Watch HPA events until a scale-up decision appears.
    # Returns the timestamp (ms) of the first ScalingReplicaSet/SuccessfulRescale event.
    local deadline=$(( $(now_s) + 300 ))
    local hpa_name="$1"
    while (( $(now_s) < deadline )); do
        local event_time
        event_time=$(kubectl get events -n "${NAMESPACE}" \
            --field-selector="involvedObject.name=${hpa_name}" \
            --sort-by='.lastTimestamp' -o json 2>/dev/null \
            | jq -r '[.items[] | select(.reason=="SuccessfulRescale" or .reason=="ScalingReplicaSet")] | last | .lastTimestamp // empty' \
            2>/dev/null) || true
        if [[ -n "$event_time" ]]; then
            # Convert ISO8601 to epoch ms
            echo "$(date -d "${event_time}" +%s%3N 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "${event_time}" +%s%3N 2>/dev/null)"
            return 0
        fi
        sleep 3
    done
    echo ""
}

wait_for_new_pod_ready() {
    # Wait until the StatefulSet has more Ready replicas than MIN_REPLICAS.
    # Returns the timestamp (ms) when the first new pod reached Ready.
    local deadline=$(( $(now_s) + 300 ))
    while (( $(now_s) < deadline )); do
        local ready
        ready=$(kubectl get statefulset "${STATEFULSET}" -n "${NAMESPACE}" \
            -o jsonpath='{.status.readyReplicas}' 2>/dev/null) || ready=0
        if (( ready > MIN_REPLICAS )); then
            echo "$(now_ms)"
            return 0
        fi
        sleep 3
    done
    echo ""
}

ms_to_s() {
    # Convert millisecond difference to seconds with 1 decimal place.
    local diff="$1"
    if [[ -z "$diff" || "$diff" == "null" ]]; then echo "N/A"; return; fi
    echo "$(echo "scale=1; $diff / 1000" | bc -l)"
}

# ── Main ──────────────────────────────────────────────────────────────────────
hdr "PRESYNC Controlled Burst Experiment"
echo "  Mode         : ${MODE}"
echo "  Runs per mode: ${N_RUNS}"
echo "  Burst duration: ${BURST_DURATION_S}s"
echo "  PSI threshold : ${PSI_THRESHOLD}%"
echo "  StatefulSet  : ${NAMESPACE}/${STATEFULSET} (min=${MIN_REPLICAS} max=${MAX_REPLICAS})"
echo ""

# Verify prerequisites
hdr "Prerequisites"
for cmd in kubectl jq bc curl; do
    if command -v "$cmd" &>/dev/null; then ok "$cmd found"
    else err "$cmd not found — install it and re-run"; exit 1; fi
done

kubectl cluster-info &>/dev/null && ok "Kubernetes cluster reachable" \
    || { err "kubectl cannot reach cluster"; exit 1; }

kubectl get statefulset "${STATEFULSET}" -n "${NAMESPACE}" &>/dev/null \
    && ok "StatefulSet ${STATEFULSET} exists" \
    || { err "StatefulSet ${STATEFULSET} not found in ${NAMESPACE}"; exit 1; }

# Results directory
mkdir -p "${RESULTS_DIR}"
CSV="${RESULTS_DIR}/${LOG_PREFIX}.csv"
echo "run,mode,T_onset_ms,T_psi_ms,T_hpa_ms,T_ready_ms,t_detect_s,t_hpa_s,t_ready_s,psi_at_onset" \
    > "${CSV}"

# Determine which modes to run
declare -a MODES_TO_RUN
case "${MODE}" in
    reactive)   MODES_TO_RUN=("reactive") ;;
    predictive) MODES_TO_RUN=("predictive") ;;
    both)       MODES_TO_RUN=("reactive" "predictive") ;;
    *) err "Unknown MODE=${MODE}"; exit 1 ;;
esac

declare -A reactive_ready_times predictive_ready_times

run_num=0
for mode in "${MODES_TO_RUN[@]}"; do
    hdr "Mode: ${mode^^}  (${N_RUNS} runs)"
    declare -a ready_times=()

    for (( i=1; i<=N_RUNS; i++ )); do
        (( run_num++ ))
        hdr "  Run ${run_num}  (${mode}, attempt ${i}/${N_RUNS})"

        # 1. Reset to min replicas
        reset_to_min_replicas

        # 2. Apply the right HPA
        apply_hpa "${mode}"

        # 3. Wait for PSI to settle
        wait_for_psi_below 0.5 30 || warn "Proceeding without full PSI settle"

        # Clear stale HPA events before this run
        # (kubectl does not expose a delete-events API, so we note the current time)
        run_start_epoch=$(now_s)
        psi_at_onset=$(query_psi)
        psi_at_onset="${psi_at_onset:-0}"

        # 4. Inject burst and record onset timestamp
        T_onset=$(now_ms)
        info "T_onset = ${T_onset} ms"
        inject_io_burst

        # 5. Wait for PSI to cross threshold
        T_psi=$(wait_for_psi_spike)
        if [[ -z "$T_psi" ]]; then
            warn "PSI never crossed ${PSI_THRESHOLD}% — skipping run"
            echo "${run_num},${mode},${T_onset},N/A,N/A,N/A,N/A,N/A,N/A,${psi_at_onset}" >> "${CSV}"
            continue
        fi
        t_detect=$(ms_to_s $(( T_psi - T_onset )))
        info "T_psi = ${T_psi} ms  (t_detect=${t_detect}s)"

        # 6. Wait for HPA scale-up decision
        hpa_name="workload-${mode}-hpa"
        T_hpa=$(wait_for_hpa_scaleup "${hpa_name}")
        t_hpa=$(ms_to_s $(( T_hpa - T_onset )) 2>/dev/null) || t_hpa="N/A"
        info "T_hpa  = ${T_hpa:-N/A} ms  (t_hpa=${t_hpa}s)"

        # 7. Wait for new pod Ready
        T_ready=$(wait_for_new_pod_ready)
        if [[ -z "$T_ready" ]]; then
            warn "No new pod became Ready within timeout"
            T_ready="N/A"
            t_ready="N/A"
        else
            t_ready=$(ms_to_s $(( T_ready - T_onset )))
            ready_times+=( "${t_ready}" )
        fi
        info "T_ready= ${T_ready} ms  (t_ready=${t_ready}s)"

        # 8. Record
        echo "${run_num},${mode},${T_onset},${T_psi},${T_hpa:-N/A},${T_ready},${t_detect},${t_hpa},${t_ready},${psi_at_onset}" \
            >> "${CSV}"

        ok "Run ${run_num} done: onset→PSI=${t_detect}s  onset→HPA=${t_hpa}s  onset→Ready=${t_ready}s"

        # Let cluster recover between runs (scale-down stabilisation window = 300 s)
        if (( i < N_RUNS )); then
            info "Waiting 180s for cluster to recover before next run …"
            sleep 180
        fi
    done

    if [[ "${mode}" == "reactive" ]]; then
        reactive_ready_times=( "${ready_times[@]+"${ready_times[@]}"}" )
    else
        predictive_ready_times=( "${ready_times[@]+"${ready_times[@]}"}" )
    fi
done

# ── Summary table ─────────────────────────────────────────────────────────────
hdr "RESULTS SUMMARY"
echo "Full data: ${CSV}"
echo ""
echo "Per-run results:"
printf "%-6s %-12s %-12s %-12s %-12s\n" "Run" "Mode" "t_detect(s)" "t_hpa(s)" "t_ready(s)"
printf "%-6s %-12s %-12s %-12s %-12s\n" "---" "----" "-----------" "--------" "----------"
while IFS=, read -r run mode t_onset t_psi t_hpa t_ready t_detect t_hpa_s t_ready_s psi_at; do
    [[ "$run" == "run" ]] && continue
    printf "%-6s %-12s %-12s %-12s %-12s\n" \
        "${run}" "${mode}" "${t_detect}" "${t_hpa_s}" "${t_ready_s}"
done < "${CSV}"

echo ""
# Compute mean onset-to-Ready per mode using python (available on the host)
python3 - "${CSV}" << 'PYEOF'
import csv, sys
from statistics import mean, stdev

rows = list(csv.DictReader(open(sys.argv[1])))
for mode in ('reactive', 'predictive'):
    vals = []
    for r in rows:
        try:
            v = float(r['t_ready_s'])
            if r['mode'] == mode:
                vals.append(v)
        except (ValueError, KeyError):
            pass
    if vals:
        m = mean(vals)
        s = stdev(vals) if len(vals) > 1 else 0.0
        print(f"  {mode:12s}  onset→Ready  mean={m:.1f}s  std={s:.1f}s  n={len(vals)}")
    else:
        print(f"  {mode:12s}  no valid runs recorded")

# Lead-time advantage
reactive_vals  = [float(r['t_ready_s']) for r in rows if r['mode']=='reactive'  and r['t_ready_s'] not in ('N/A','')]
predictive_vals= [float(r['t_ready_s']) for r in rows if r['mode']=='predictive' and r['t_ready_s'] not in ('N/A','')]
if reactive_vals and predictive_vals:
    adv = mean(reactive_vals) - mean(predictive_vals)
    print(f"\n  Predictive advantage : {adv:+.1f}s")
    print(f"  Relative reduction   : {adv/mean(reactive_vals)*100:+.1f}%")
PYEOF

echo ""
ok "Experiment complete — results in ${RESULTS_DIR}/"
