#!/usr/bin/env bash
# Run NscSceneSnapshot in a verification checkout. Usage:
#   run_snapshot.sh <checkout (bash path)> <out file (Windows path ok)> <log file> [--perturb]
# Copies the scratch Editor script in if missing; does not remove it (see cleanup_snapshot.sh).
set -u
CO="$1"; OUT="$2"; LOG="$3"; PERTURB="${4:-}"
UNITY="/c/Program Files/Unity/Hub/Editor/6000.1.8f1/Editor/Unity.exe"
SRC=/c/nscrev/reports/nsc077/evidence-tools/NscSceneSnapshot.cs
if tasklist //FI "IMAGENAME eq Unity.exe" | grep -q Unity.exe; then echo "Unity is running; stop"; exit 2; fi
mkdir -p "$CO/Assets/_NscEvidence/Editor"
cp "$SRC" "$CO/Assets/_NscEvidence/Editor/NscSceneSnapshot.cs"
EXTRA=""
[ "$PERTURB" = "--perturb" ] && EXTRA="-snapshotPerturb"
WIN_CO=$(cygpath -m "$CO")
"$UNITY" -batchmode -quit -projectPath "$WIN_CO" -executeMethod NscEvidence.NscSceneSnapshot.Run -snapshotOut "$OUT" $EXTRA -logFile "$LOG"
RC=$?
echo "unity exit $RC"
grep -a -E "NSC scene snapshot|error CS|Exception" "$LOG" | head -8
exit $RC
