#!/bin/bash
# Build the app for the iPad simulator, start it and take pictures (out/sim_*.png), with the game's log (out/sim_log.txt).
# Runs in the GitHub workflow after make_www.py --test, npx cap add ios / sync and ios_setup.py.
set -uo pipefail
OUT="${OUT:-$PWD/out}"; mkdir -p "$OUT"
HERE="$(cd "$(dirname "$0")" && pwd)"
BID=$(python3 -c "import json;print(json.load(open('$HERE/capacitor.config.json'))['appId'])")
cd "$HERE/ios/App"
if [ -d App.xcworkspace ]; then W=(-workspace App.xcworkspace); else W=(-project App.xcodeproj); fi
echo "== building for the simulator" | tee -a "$OUT/status.txt"
xcodebuild "${W[@]}" -scheme App -configuration Debug -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$RUNNER_TEMP/simbuild" CODE_SIGNING_ALLOWED=NO build > "$OUT/sim_build.txt" 2>&1
st=$?; tail -25 "$OUT/sim_build.txt"
if [ $st -ne 0 ]; then echo "SIMULATOR BUILD FAILED" | tee -a "$OUT/status.txt"; grep -E "error:" "$OUT/sim_build.txt" | head -20 >> "$OUT/status.txt"; exit 1; fi
APPP=$(ls -d "$RUNNER_TEMP"/simbuild/Build/Products/Debug-iphonesimulator/*.app | head -1)
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
sys.stderr.write((best[2]+" "+best[3]) if best else "no iPad simulator")')
echo "== iPad simulator: $DEV" | tee -a "$OUT/status.txt"
[ -z "$DEV" ] && { echo "NO IPAD SIMULATOR" | tee -a "$OUT/status.txt"; exit 1; }
xcrun simctl boot "$DEV" || true
xcrun simctl bootstatus "$DEV" -b > /dev/null 2>&1 || true
xcrun simctl install "$DEV" "$APPP" || { echo "INSTALL FAILED" | tee -a "$OUT/status.txt"; exit 1; }
xcrun simctl launch --console-pty "$DEV" "$BID" > "$OUT/sim_console.txt" 2>&1 &
LP=$!
for t in 30 60 90 120 150; do sleep 30; xcrun simctl io "$DEV" screenshot "$OUT/sim_${t}s.png" > /dev/null 2>&1 || true; done
xcrun simctl terminate "$DEV" "$BID" > /dev/null 2>&1 || true
sleep 2; kill $LP > /dev/null 2>&1 || true
grep -a "BBTEST\|ERROR\|rror" "$OUT/sim_console.txt" | head -200 > "$OUT/sim_log.txt" || true
echo "== simulator log:" | tee -a "$OUT/status.txt"; head -60 "$OUT/sim_log.txt" | tee -a "$OUT/status.txt"
xcrun simctl shutdown "$DEV" > /dev/null 2>&1 || true
exit 0
