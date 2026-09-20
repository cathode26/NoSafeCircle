#!/usr/bin/env bash
# NSC-089 VAL-001, the half the clean runner cannot cover.
#
# VAL-001 asks for three things. The EditMode fixture covers the first on its own:
#   NavMeshAgentConfigurationTests.CommittedScene_HasSingleGameplayNavigationOwner_...
# already asserts, against the COMMITTED canonical scene, that the legacy Floor is gone, that
# exactly one GameplayNavigation root and one GameplayNavigationSurface survive, that the surface
# bakes with the project agent type from PhysicsColliders (never Tilemap renderers), that the
# composed RuinedEntry FloorCollision exists, and that a test-owned NavMeshAgent using the project
# agent type computes a PathComplete across it - then closes without saving and byte-compares the
# scene file. The fixture's own comment names this as the check the pipeline re-runs.
#
# The other two things are what this script does:
#   (2) run the authorized builder, then re-run that check against the BUILT scene;
#   (3) repeat the builder and re-check, proving exactly one navigation owner still survives.
#
# It deliberately does NOT use run_unity_tests_clean.ps1 for steps 2 and 3: the builder dirties the
# committed scene on purpose, and that runner refuses a dirty worktree. The BOUND manifest comes
# from the clean run at the validated commit; these two are supplementary evidence, the same shape
# NSC-069's VAL-003 two-builds pass used. The checkout is restored at the end.
#
# One Unity at a time. Run nothing else while this runs.
set -u

CO=/c/nscrev/branch-verify
UNITY="/c/Program Files/Unity/Hub/Editor/6000.1.8f1/Editor/Unity.exe"
OUT=/c/nscrev/reports/delivery/NSC-089/val001-rebuild-recheck
FILTER="NoSafeCircle.DoorPrototype.Tests.Editor.NavMeshAgentConfigurationTests"
SCENE="$CO/Assets/Scenes/DoorPrototype.unity"
WIN_CO=$(cygpath -m "$CO")
WIN_OUT=$(cygpath -m "$OUT")
EXPECTED_COMMIT=2559514826e919bea243e1bf6fda4ad73462ac62

if tasklist //FI "IMAGENAME eq Unity.exe" 2>/dev/null | grep -qi "unity.exe"; then
  echo "ABORT: a Unity is already running - one at a time"; exit 2
fi
actual=$(git -C "$CO" rev-parse HEAD)
if [ "$actual" != "$EXPECTED_COMMIT" ]; then
  echo "ABORT: checkout is at $actual, expected $EXPECTED_COMMIT"; exit 2
fi
if [ -n "$(git -C "$CO" status --porcelain --untracked-files=all)" ]; then
  echo "ABORT: checkout is dirty before we start"
  git -C "$CO" status --porcelain --untracked-files=all | head; exit 2
fi

mkdir -p "$OUT"
echo "HEAD: $actual"
echo "committed scene sha256: $(sha256sum "$SCENE" | cut -d' ' -f1)"

for n in 1 2; do
  echo "=== builder materialization $n ==="
  "$UNITY" -batchmode -quit -nographics -projectPath "$WIN_CO" \
    -executeMethod NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build \
    -logFile "$WIN_OUT/build$n.log"
  echo "builder $n exit: $?"
  echo "scene sha256 after build $n: $(sha256sum "$SCENE" | cut -d' ' -f1)"
  git -C "$CO" status --porcelain --untracked-files=all > "$OUT/dirty-after-build$n.txt"
  echo "dirty paths after build $n: $(wc -l < "$OUT/dirty-after-build$n.txt")"

  echo "=== VAL-001 recheck $n (EditMode, against the BUILT scene) ==="
  # Argument list copied from Pipeline/Testing/run_unity_tests_clean.ps1:402-410, deliberately.
  # -runTests must NOT be combined with -quit: Unity honours -quit first and exits before the test
  # runner executes, so it returns 0 and writes no XML. That is what the first attempt at this
  # script did. -nographics is also absent there; do not add it back.
  rm -f "$CO/Library/ilpp.pid"
  "$UNITY" -batchmode -projectPath "$WIN_CO" \
    -runTests -testPlatform EditMode -testFilter "$FILTER" \
    -testResults "$WIN_OUT/recheck$n.xml" -logFile "$WIN_OUT/recheck$n.log"
  echo "recheck $n exit: $?"
  # Read the counts out of the XML, never out of the console. A run that selects zero tests
  # reports total=0 and exits 0; that is a FAILURE here, not a pass.
  echo "recheck $n:"
  python -B /c/nscrev/reports/delivery/NSC-089/check_recheck_xml.py "$OUT/recheck$n.xml" 2 \
    || echo "  RECHECK $n DID NOT MEET total=2 failed=0 - read the XML before believing anything"
done

echo "=== restoring the checkout ==="
git -C "$CO" checkout -- .
git -C "$CO" clean -fd >/dev/null 2>&1
echo "checkout restored: $(git -C "$CO" status --porcelain --untracked-files=all | wc -l) changes"
echo "HEAD still: $(git -C "$CO" rev-parse HEAD)"
echo "committed scene sha256 restored: $(sha256sum "$SCENE" | cut -d' ' -f1)"
