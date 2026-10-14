    # R55: selected-module readiness above remains a module-only statement.
    # This runs in the already-asynchronous vendor.modprobe service, never GKI.
    r55_late_dsp_start() (
        r55_log() { printf 'R55_DSP target=%s event=%s %s\n' "$1" "$2" "$3"; }
        r55_firmware_file() {
            # Only the existing stock ueventd firmware search directories.
            for r55_dir in /etc/firmware /odm/firmware /vendor/firmware /firmware/image \
                /vendor/firmware_mnt/image /vendor/modem_firmware/image \
                /vendor/soccp_firmware/image /vendor/vm-system; do
                if [ -r "$r55_dir/$1" ] && [ -s "$r55_dir/$1" ]; then
                    printf '%s\n' "$r55_dir/$1"
                    return 0
                fi
            done
            return 1
        }
        r55_identity() {
            r55_check_node=$1
            r55_check_base=${r55_check_node##*/}
            case "$r55_check_base" in
                remoteproc*) r55_check_index=${r55_check_base#remoteproc} ;;
                *) return 1 ;;
            esac
            case "$r55_check_index" in ''|*[!0-9]*) return 1 ;; esac
            [ "$("$TIMEOUT" cat "$r55_check_node/name" 2>/dev/null)" = "$r55_name" ] || return 1
            [ "$("$TIMEOUT" cat "$r55_check_node/firmware" 2>/dev/null)" = "$r55_firmware" ] || return 1
            r55_parent=/sys/devices/platform/soc/$r55_name
            [ "$("$TIMEOUT" readlink -f "$r55_check_node" 2>/dev/null)" = \
                "$r55_parent/remoteproc/$r55_check_base" ] || return 1
            [ "$("$TIMEOUT" readlink -f "$r55_parent/of_node" 2>/dev/null)" = \
                "/sys/firmware/devicetree/base/soc/$r55_of_name" ] || return 1
            [ "$("$TIMEOUT" tr '\000' '\n' < "$r55_parent/of_node/compatible" 2>/dev/null)" = \
                "$r55_compatible" ] || return 1
            [ -r "$r55_check_node/state" ] && [ -w "$r55_check_node/state" ]
        }
        r55_worker() (
            r55_target=$1
            case "$r55_target" in
                adsp)
                    r55_name=3000000.remoteproc-adsp
                    r55_of_name=remoteproc-adsp@03000000
                    r55_compatible=qcom,canoe-adsp-pas
                    r55_firmware=adsp.mdt
                    r55_dtb_firmware=adsp_dtb.mdt
                    ;;
                cdsp)
                    r55_name=32300000.remoteproc-cdsp
                    r55_of_name=remoteproc-cdsp@32300000
                    r55_compatible=qcom,canoe-cdsp-pas
                    r55_firmware=cdsp.mdt
                    r55_dtb_firmware=cdsp_dtb.mdt
                    ;;
                *) r55_log unknown REFUSED 'invalid_target'; return 1 ;;
            esac
            r55_log "$r55_target" WAIT_READY 'budget_s=15'
            r55_ready=0
            r55_tick=0
            while [ "$r55_tick" -lt 15 ]; do
                r55_fallback=$("$TIMEOUT" cat /proc/sys/kernel/firmware_config/force_sysfs_fallback 2>/dev/null) || r55_fallback=unreadable
                r55_ueventd=$(getprop init.svc.ueventd)
                r55_coldboot=$(getprop ro.cold_boot_done)
                r55_mdt=$(r55_firmware_file "$r55_firmware") || r55_mdt=
                r55_dtb=$(r55_firmware_file "$r55_dtb_firmware") || r55_dtb=
                if [ "$r55_fallback" = 1 ] && [ "$r55_ueventd" = running ] && \
                    [ "$r55_coldboot" = true ] && [ -n "$r55_mdt" ] && [ -n "$r55_dtb" ]; then
                    r55_ready=1
                    break
                fi
                sleep 1 || return 1
                r55_tick=$((r55_tick + 1))
            done
            if [ "$r55_ready" != 1 ]; then
                r55_log "$r55_target" NOT_READY "fallback=$r55_fallback ueventd=$r55_ueventd coldboot=$r55_coldboot mdt=$r55_mdt dtb=$r55_dtb; no_write"
                return 1
            fi
            r55_count=0
            r55_node=
            for r55_candidate in /sys/class/remoteproc/remoteproc*; do
                [ -e "$r55_candidate/name" ] || continue
                r55_candidate_name=$("$TIMEOUT" cat "$r55_candidate/name" 2>/dev/null) || continue
                [ "$r55_candidate_name" = "$r55_name" ] || continue
                r55_count=$((r55_count + 1))
                r55_node=$r55_candidate
            done
            if [ "$r55_count" -ne 1 ] || ! r55_identity "$r55_node"; then
                r55_log "$r55_target" IDENTITY_REFUSED "matches=$r55_count node=$r55_node; no_write"
                return 1
            fi
            r55_state=$("$TIMEOUT" cat "$r55_node/state" 2>/dev/null) || r55_state=unreadable
            case "$r55_state" in
                running) r55_log "$r55_target" ALREADY_RUNNING "node=$r55_node; no_write"; return 0 ;;
                offline) ;;
                *) r55_log "$r55_target" STATE_SKIPPED "node=$r55_node state=$r55_state; no_write"; return 1 ;;
            esac
            r55_identity "$r55_node" || { r55_log "$r55_target" IDENTITY_CHANGED 'no_write'; return 1; }
            r55_log "$r55_target" START_ONCE "node=$r55_node mdt=$r55_mdt dtb=$r55_dtb budget_s=20"
            # Read state again inside the timed child immediately before writing.
            # The kernel has no offline CAS: a competing user can add a power vote.
            # Never stop, detach, SSR, or retry to compensate for that narrow race.
            "$TIMEOUT" timeout -k 2 20 /vendor/bin/sh -c '
                IFS= read -r r55_now < "$1" || exit 4
                [ "$r55_now" = offline ] || exit 3
                printf "start\n" > "$1"
            ' r55-dsp-write "$r55_node/state"
            r55_write_rc=$?
            r55_after=$("$TIMEOUT" cat "$r55_node/state" 2>/dev/null) || r55_after=unreadable
            if [ "$r55_after" = running ]; then
                r55_log "$r55_target" RUNNING "node=$r55_node writer_rc=$r55_write_rc; firmware_QMI_audio_readiness_not_claimed"
                return 0
            fi
            r55_log "$r55_target" START_UNCONFIRMED "node=$r55_node state=$r55_after writer_rc=$r55_write_rc; no_retry"
            return 1
        )
        # choose_timeout already proved this applet before any module was loaded.
        # Repeat the no-op probe here; failure never revokes selected-module ready.
        if ! "$TIMEOUT" timeout -k 2 1 "$TIMEOUT" true >/dev/null 2>&1; then
            r55_log all TOOL_UNAVAILABLE 'timeout_probe_failed; no_write'
            return 1
        fi
        r55_log all BEGIN 'module_gate_already_complete=213/213 supervisor_budget_s=45'
        r55_worker adsp &
        r55_adsp_pid=$!
        r55_worker cdsp &
        r55_cdsp_pid=$!
        r55_elapsed=0
        r55_adsp_done=0
        r55_cdsp_done=0
        while [ "$r55_elapsed" -lt 45 ]; do
            if [ "$r55_adsp_done" = 0 ] && ! kill -0 "$r55_adsp_pid" 2>/dev/null; then
                wait "$r55_adsp_pid"; r55_rc=$?
                r55_log adsp WORKER_EXIT "rc=$r55_rc"
                r55_adsp_done=1
            fi
            if [ "$r55_cdsp_done" = 0 ] && ! kill -0 "$r55_cdsp_pid" 2>/dev/null; then
                wait "$r55_cdsp_pid"; r55_rc=$?
                r55_log cdsp WORKER_EXIT "rc=$r55_rc"
                r55_cdsp_done=1
            fi
            [ "$r55_adsp_done$r55_cdsp_done" = 11 ] && break
            sleep 1 || break
            r55_elapsed=$((r55_elapsed + 1))
        done
        for r55_pair in "adsp:$r55_adsp_pid:$r55_adsp_done" "cdsp:$r55_cdsp_pid:$r55_cdsp_done"; do
            r55_target=${r55_pair%%:*}
            r55_rest=${r55_pair#*:}
            r55_pid=${r55_rest%%:*}
            r55_done=${r55_rest##*:}
            if [ "$r55_done" = 0 ]; then
                r55_log "$r55_target" SUPERVISOR_TIMEOUT 'worker_state_unknown; no_wait_no_retry'
                kill -TERM "$r55_pid" 2>/dev/null || :
                kill -KILL "$r55_pid" 2>/dev/null || :
                # Do not wait: a kernel firmware write could be uninterruptible.
            fi
        done
        r55_log all END "elapsed_s=$r55_elapsed; selected_module_ready_unchanged DSP_result_in_per_target_markers"
        return 0
    )
    r55_late_dsp_start || say 'R55_DSP helper_failed; selected module readiness retained'
