#!/usr/bin/env bash
# NSC-077 final verification in branch-verify (contract rev 10 VAL-007 flow). Usage: final_verify.sh <candidate sha> <label>
# 1) detach at the candidate  2) Build 1 + manifest  3) Build 2 + manifest, non-scene outputs must match
# 4) commit builder output (scene from Build 2)  5) Edit Mode, Play Mode, Play Mode again (flake check)
set -u
SHA="$1"; LABEL="$2"
V=/c/nscrev/branch-verify
R=/c/nscrev/reports/nsc077/unity
T=/c/nscrev/reports/nsc077/evidence-tools
U="/c/Program Files/Unity/Hub/Editor/6000.1.8f1/Editor/Unity.exe"
EDIT="NoSafeCircle.DoorPrototype.Tests.Editor.EnemyArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.WizardArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests"
PLAY="NoSafeCircle.DoorPrototype.Tests.EnemyAnimationPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLanternWispCasterPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitDoorCrossingPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyTargetKnowledgePlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyHealthPlayModeTests;NoSafeCircle.DoorPrototype.Tests.ActiveEnemyRegistryPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLockedDoorAttackPlayModeTests;NoSafeCircle.DoorPrototype.Tests.DoorEnemyPassabilityPlayModeTests;NoSafeCircle.DoorPrototype.Tests.WizardAnimationPlayModeTests"

step() { echo "[$(date -u +%H:%M:%SZ)] $*"; }
if tasklist //FI "IMAGENAME eq Unity.exe" | grep -q Unity.exe; then step "STOP: Unity is running"; exit 2; fi
[ -z "$(git -C $V status --porcelain)" ] || { step "STOP: branch-verify dirty"; exit 2; }
git -C /c/NSC/NSC/NoSafeCircle fetch -q /c/nscrev/nsc077-codex +codex/nsc077-moving-enemy-art-20260917:refs/heads/codex/nsc077-moving-enemy-art-20260917 || exit 1
git -C $V checkout -q --detach "$SHA" || exit 1
step "candidate $(git -C $V rev-parse HEAD) base $(git -C $V rev-parse --short "$SHA~8")"

for n in 1 2; do
  "$U" -batchmode -quit -projectPath C:/nscrev/branch-verify -executeMethod NoSafeCircle.DoorPrototype.Editor.DoorPrototypeSceneBuilder.Build -logFile "C:/nscrev/reports/nsc077/unity/$LABEL-build$n.log"
  rc=$?; errs=$(grep -a -c "error CS" "$R/$LABEL-build$n.log")
  step "build $n exit $rc compile errors $errs"
  [ $rc -eq 0 ] && [ "$errs" = "0" ] || { step "STOP: build $n failed"; exit 1; }
  bash $T/build_manifest.sh $V "$R/$LABEL-build$n" 2>/dev/null | tail -1
done
cmp -s "$R/$LABEL-build1-status.txt" "$R/$LABEL-build2-status.txt" || { step "STOP: changed path sets differ between builds"; exit 1; }
if ! cmp -s <(grep -v "Assets/Scenes/DoorPrototype.unity" "$R/$LABEL-build1-hashes.txt") <(grep -v "Assets/Scenes/DoorPrototype.unity" "$R/$LABEL-build2-hashes.txt"); then
  step "STOP: non-scene generated files differ between builds"; exit 1
fi
step "VAL-007: $(grep -vc 'Assets/Scenes/DoorPrototype.unity' "$R/$LABEL-build2-hashes.txt") non-scene generated files byte-identical across builds"

cut -c4- "$R/$LABEL-build2-status.txt" > "$R/$LABEL-materialize-paths.txt"
git -C $V add --pathspec-from-file="C:/nscrev/reports/nsc077/unity/$LABEL-materialize-paths.txt" 2>/dev/null
git -C $V -c user.name="No Safe Circle Branch Recovery" -c user.email="branch-recovery@nosafecircle.invalid" commit -q -F C:/nscrev/reports/nsc077/materialize-message.txt || { step "STOP: commit failed"; exit 1; }
[ -z "$(git -C $V status --porcelain)" ] || { step "STOP: tree dirty after commit"; exit 1; }
M=$(git -C $V rev-parse HEAD)
git -C /c/NSC/NSC/NoSafeCircle update-ref "refs/archive/nsc077-$LABEL-materialize" "$M"
step "materialize commit $M ($(git -C $V show --name-status --format= HEAD | wc -l) paths)"

run_tests() {
  platform="$1"; filter="$2"; log="$3"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\nscrev\branch-verify\Pipeline\Testing\run_unity_tests_clean.ps1' -TestPlatform "$platform" -TestFilter "$filter" -ProjectPath 'C:\nscrev\branch-verify' > "$log" 2>&1
  rc=$?
  xml=$(grep -a -o "C:[^ ]*test-results.xml" "$log" | head -1 | tr -d '\r')
  summary=$(python -B -c "
import sys, xml.etree.ElementTree as ET
r=ET.parse(sys.argv[1]).getroot()
fails=[tc.get('fullname') for tc in r.iter('test-case') if tc.get('result')!='Passed']
zero=[ts.get('name') for ts in r.iter('test-suite') if ts.get('type')=='TestFixture' and ts.get('total')=='0']
print('total',r.get('total'),'passed',r.get('passed'),'failed',r.get('failed'),'| failures:',fails or 'none','| empty fixtures:',zero or 'none')
" "$xml" 2>&1)
  step "$platform exit $rc: $summary"
}
run_tests EditMode "$EDIT" "$R/$LABEL-editmode.log"
run_tests PlayMode "$PLAY" "$R/$LABEL-playmode.log"
run_tests PlayMode "$PLAY" "$R/$LABEL-playmode-2.log"
step "final tree: $(git -C $V status --porcelain | wc -l) dirty paths; HEAD $(git -C $V rev-parse --short HEAD)"
