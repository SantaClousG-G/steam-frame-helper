#!/bin/bash
# Records Wi-Fi state on Steam Frame once per second for streaming diagnostics.
# Usage: wifi_record.sh <seconds> <output.csv>
# Columns: time, iface, signal, tx_bitrate, rx_bitrate, tx_retries, tx_failed,
#          tx_bytes, rx_bytes, busy_ms, active_ms (channel survey of the operating freq)
set -u
DURATION="${1:-600}"
OUT="${2:-$HOME/wifi_record.csv}"
END=$(( $(date +%s) + DURATION ))
echo "time,iface,signal,tx_bitrate,rx_bitrate,tx_retries,tx_failed,tx_bytes,rx_bytes,busy_ms,active_ms" > "$OUT"

survey() {
    # channel busy/active counters for the in-use frequency (needs root)
    sudo -n iw dev "$1" survey dump 2>/dev/null | awk '
        /frequency:/ { inuse = ($0 ~ /in use/) }
        inuse && /channel active time:/ { a = $4 }
        inuse && /channel busy time:/   { b = $4 }
        END { printf "%s,%s", b, a }'
}

while [ "$(date +%s)" -lt "$END" ]; do
    T=$(date +%H:%M:%S.%N | cut -c1-12)
    for IF in wlan0 wlanap; do
        iw dev "$IF" station dump 2>/dev/null | awk -v t="$T" -v ifc="$IF" -v sv="$(survey "$IF")" '
            /^Station/ { if (n++) exit }
            /signal:/ && !sig { sig = $2 }
            /tx bitrate:/ { txb = $3 }
            /rx bitrate:/ { rxb = $3 }
            /tx retries:/ { txr = $3 }
            /tx failed:/  { txf = $3 }
            /tx bytes:/   { txB = $3 }
            /rx bytes:/   { rxB = $3 }
            END { if (n) printf "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n", t, ifc, sig, txb, rxb, txr, txf, txB, rxB, sv }' >> "$OUT"
    done
    sleep 1
done
echo "done: $OUT"
