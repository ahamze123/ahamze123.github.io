#!/bin/bash
# Make the App Store build and send it to App Store Connect (TestFlight). Runs in the GitHub workflow when the Apple key
# is in the repository secrets: ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_P8 (the whole .p8 file) and APPLE_TEAM_ID.
set -uo pipefail
OUT="${OUT:-$PWD/out}"; mkdir -p "$OUT"
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
BID=$(python3 -c "import json;print(json.load(open('capacitor.config.json'))['appId'])")
VER=$(python3 -c "import json;print(json.load(open('build.json'))['version'])")
BUILD="${BUILD:-1}"
KEY=~/private_keys/AuthKey_${ASC_KEY_ID}.p8; mkdir -p ~/private_keys; printf '%s\n' "$ASC_KEY_P8" > "$KEY"; chmod 600 "$KEY"
python3 -m venv "$RUNNER_TEMP/v" > /dev/null && "$RUNNER_TEMP/v/bin/pip" -q install pyjwt cryptography > /dev/null
R=$("$RUNNER_TEMP/v/bin/python" asc.py prepare "$BID" "Block Buddies")
echo "== App Store Connect: $R" | tee -a "$OUT/status.txt"
case "$R" in
  READY*) ;;
  NO_APP*) echo "NEXT: make the app in App Store Connect (Apps, +, New App, bundle ID $BID), then run this again" | tee -a "$OUT/status.txt"; exit 0;;
  *) echo "UPLOAD STOPPED" | tee -a "$OUT/status.txt"; exit 1;;
esac
cd ios/App
if [ -d App.xcworkspace ]; then W=(-workspace App.xcworkspace); else W=(-project App.xcodeproj); fi
echo "== archive $VER ($BUILD)" | tee -a "$OUT/status.txt"
xcodebuild "${W[@]}" -scheme App -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -archivePath "$RUNNER_TEMP/App.xcarchive" MARKETING_VERSION="$VER" CURRENT_PROJECT_VERSION="$BUILD" \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" CODE_SIGNING_ALLOWED=NO archive > "$OUT/archive.txt" 2>&1
st=$?; tail -15 "$OUT/archive.txt"
if [ $st -ne 0 ]; then echo "ARCHIVE FAILED" | tee -a "$OUT/status.txt"; grep -E "error:" "$OUT/archive.txt" | head -20 >> "$OUT/status.txt"; exit 1; fi
sed "s/TEAM_ID/$APPLE_TEAM_ID/" "$HERE/ExportOptions.plist" > "$RUNNER_TEMP/ExportOptions.plist"
echo "== sign and upload" | tee -a "$OUT/status.txt"
xcodebuild -exportArchive -archivePath "$RUNNER_TEMP/App.xcarchive" -exportOptionsPlist "$RUNNER_TEMP/ExportOptions.plist" \
  -exportPath "$RUNNER_TEMP/export" -allowProvisioningUpdates \
  -authenticationKeyPath "$KEY" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID" > "$OUT/export.txt" 2>&1
st=$?; tail -25 "$OUT/export.txt"
if [ $st -ne 0 ]; then echo "UPLOAD FAILED" | tee -a "$OUT/status.txt"; grep -iE "error|fail" "$OUT/export.txt" | head -20 >> "$OUT/status.txt"; exit 1; fi
echo "UPLOADED $VER ($BUILD): it shows in App Store Connect and TestFlight after Apple processes it (10-30 minutes)" | tee -a "$OUT/status.txt"
