#!/bin/bash
# Try the app on an iPad simulator, in three parts (each its own step in the GitHub workflow, so a slow part shows up):
#   sim_test.sh build   build the app for the simulator
#   sim_test.sh boot    start an iPad simulator (the biggest iPad Pro there is)
#   sim_test.sh run     install the app, start it, take pictures (out/sim_*.png) and keep the game's log (out/sim_log.txt)
set -uo pipefail
OUT="${OUT:-$PWD/out}"; mkdir -p "$OUT"
HERE="$(cd "$(dirname "$0")" && pwd)"
T="${RUNNER_TEMP:-/tmp}"
BID=$(python3 -c "import json;print(json.load(open('$HERE/capacitor.config.json'))['appId'])")
case "${1:-}" in
build)
  cd "$HERE/ios/App"
  if [ -d App.xcworkspace ]; then W=(-workspace App.xcworkspace); else W=(-project App.xcodeproj); fi
  echo "== building for the simulator ($(date +%H:%M:%S))" | tee -a "$OUT/status.txt"
  xcodebuild "${W[@]}" -scheme App -configuration Debug -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
    -derivedDataPath "$T/simbuild" CODE_SIGNING_ALLOWED=NO build > "$OUT/sim_build.txt" 2>&1
  st=$?; tail -20 "$OUT/sim_build.txt"
  if [ $st -ne 0 ]; then echo "SIMULATOR BUILD FAILED" | tee -a "$OUT/status.txt"; grep -E "error:" "$OUT/sim_build.txt" | head -20 >> "$OUT/status.txt"; exit 1; fi
  ls -d "$T"/simbuild/Build/Products/Debug-iphonesimulator/*.app | head -1 > "$T/simapp"
  echo "built $(cat "$T/simapp") ($(date +%H:%M:%S))" | tee -a "$OUT/status.txt";;
boot)
  DEV=$(xcrun simctl list devices available -j | python3 -c '
import json,sys
d=json.load(sys.stdin)["devices"];best=None
for rt,L in d.items():
  if "iOS" not in rt: continue
  for x in L:
    n=x["name"]
    if "iPad" not in n: continue
    sc=(3 if ("13-inch" in n or "12.9" in n) else 2 if "Pro" in n else 1, rt)
    if best is None or sc>best[0]: best=(sc,x["udid"],n,rt)
print(best[1] if best else "")
sys.stderr.write(((best[2]+" "+best[3]) if best else "no iPad simulator")+"\n")' 2>>"$OUT/status.txt")
  [ -z "$DEV" ] && { echo "NO IPAD SIMULATOR" | tee -a "$OUT/status.txt"; xcrun simctl list devices available >> "$OUT/status.txt"; exit 1; }
  echo "$DEV" > "$T/simdev"
  echo "== booting $DEV ($(date +%H:%M:%S))" | tee -a "$OUT/status.txt"
  xcrun simctl boot "$DEV" 2>&1 | tail -3
  xcrun simctl bootstatus "$DEV" -b > "$OUT/sim_boot.txt" 2>&1
  echo "booted ($(date +%H:%M:%S))" | tee -a "$OUT/status.txt";;
run)
  DEV=$(cat "$T/simdev"); APPP=$(cat "$T/simapp")
  xcrun simctl install "$DEV" "$APPP" || { echo "INSTALL FAILED" | tee -a "$OUT/status.txt"; exit 1; }
  echo "== started the game ($(date +%H:%M:%S))" | tee -a "$OUT/status.txt"
  xcrun simctl launch --terminate-running-process --stdout="$OUT/sim_out.txt" --stderr="$OUT/sim_err.txt" "$DEV" "$BID" 2>&1 | tee -a "$OUT/status.txt"
  for t in 20 40 60 90 120; do
    sleep $(( t==20 ? 20 : (t<=60 ? 20 : 30) ))
    xcrun simctl io "$DEV" screenshot "$OUT/sim_${t}s.png" > /dev/null 2>&1 || echo "no picture at ${t}s" | tee -a "$OUT/status.txt"
  done
  xcrun simctl terminate "$DEV" "$BID" > /dev/null 2>&1 || true
  cat "$OUT/sim_out.txt" "$OUT/sim_err.txt" 2>/dev/null | grep -a "BBTEST\|rror" | head -200 > "$OUT/sim_log.txt" || true
  echo "== the game's log ($(date +%H:%M:%S)):" | tee -a "$OUT/status.txt"; head -60 "$OUT/sim_log.txt" | tee -a "$OUT/status.txt"
  xcrun simctl shutdown "$DEV" > /dev/null 2>&1 || true;;
*) echo "usage: sim_test.sh build|boot|run"; exit 2;;
esac
