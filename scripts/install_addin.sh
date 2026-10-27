#!/usr/bin/env bash
# Copies the FusionBridge add-in into Fusion's AddIns folder (macOS and Linux-style paths; see README for Windows).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
case "$(uname -s)" in
  Darwin) dest="$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/FusionBridge" ;;
  *) echo "On Windows copy the 'addin' folder to %APPDATA%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns\\FusionBridge"; exit 1 ;;
esac
mkdir -p "$dest"
cp "$here/addin/FusionBridge.py" "$here/addin/FusionBridge.manifest" "$dest/"
echo "Installed to: $dest"
echo "Next: in Fusion press Shift+S, choose FusionBridge under Add-Ins and click Run."
