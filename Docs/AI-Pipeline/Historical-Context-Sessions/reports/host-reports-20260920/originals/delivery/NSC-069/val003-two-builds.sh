#!/usr/bin/env bash
# VAL-003: prove two consecutive foundation builds produce the same global generated-root
# hierarchy, component values, catalog and object counts, without duplicates.
#
# Rebuilds are never byte-identical - recreated objects get fresh random fileIDs - so the
# comparison is semantic: a component/value snapshot plus a SerializedFile shape comparison.
# Restores the checkout afterwards; the builds mutate the committed scene on purpose.
set -u
CO=/c/nscrev/branch-verify
UNITY="/c/Program Files/Unity/Hub/Editor/6000.1.8f1/Editor/Unity.exe"
OUT=/c/nscrev/reports/delivery/NSC-069
SCENE="$CO/Assets/Scenes/DoorPrototype.unity"
WIN_CO=$(cygpath -m "$CO")

if tasklist //FI "IMAGENAME eq Unity.exe" 2>/dev/null | grep -qi "6000.1.8"; then
  echo "ABORT: an NSC Unity is already running - one at a time"; exit 2
fi
if [ -n "$(git -C $CO status --porcelain)" ]; then
  echo "ABORT: checkout is dirty before we start"; git -C $CO status --porcelain | head; exit 2
fi

echo "HEAD: $(git -C $CO rev-parse --short HEAD)"
mkdir -p "$OUT"
cp /c/nscrev/reports/nsc077/evidence-tools/NscSceneSnapshot.cs "$CO/Assets/_NscEvidence/Editor/NscSceneSnapshot.cs" 2>/dev/null || {
  mkdir -p "$CO/Assets/_NscEvidence/Editor"
  cp /c/nscrev/reports/nsc077/evidence-tools/NscSceneSnapshot.cs "$CO/Assets/_NscEvidence/Editor/NscSceneSnapshot.cs"; }

for n in 1 2; do
  echo "--- foundation build $n ---"
  "$UNITY" -batchmode -quit -nographics -projectPath "$WIN_CO" \
    -executeMethod NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build \
    -logFile "$(cygpath -m $OUT)/build$n.log"
  echo "build $n exit $?"
  cp "$SCENE" "$OUT/scene-build$n.unity"
  "$UNITY" -batchmode -quit -nographics -projectPath "$WIN_CO" \
    -executeMethod NscEvidence.NscSceneSnapshot.Run \
    -snapshotOut "$(cygpath -m $OUT)/snapshot$n.txt" -logFile "$(cygpath -m $OUT)/snapshot$n.log"
  echo "snapshot $n exit $?"
done

echo "=== semantic comparison ==="
python /c/nscrev/reports/nsc077/unity/scene_shape_compare.py "$OUT/scene-build1.unity" "$OUT/scene-build2.unity" | tail -20
echo "=== snapshot diff (empty = identical hierarchy and component values) ==="
diff "$OUT/snapshot1.txt" "$OUT/snapshot2.txt" && echo "SNAPSHOTS IDENTICAL"

rm -rf "$CO/Assets/_NscEvidence" "$CO/Assets/_NscEvidence.meta"
git -C $CO checkout -- .
echo "checkout restored: $(git -C $CO status --porcelain --untracked-files=all | wc -l) changes"
