"""Factor out the placement rule and prove both halves of it (CRLF-preserving)."""
import sys

path = sys.argv[1]
data = open(path, 'rb').read()

# 1. Route the horizontal judgement through a named rule both tests can reach.
old_inline = b"".join([
    b"                else\r\n",
    b"                {\r\n",
    b"                    // Underfoot, not merely nearby. A spawn buried inside a wall or an obstacle\r\n",
    b"                    // still samples onto the open floor just outside it within the vertical\r\n",
    b"                    // allowance; only the horizontal displacement reveals that it is not\r\n",
    b"                    // standing on navigable floor at all.\r\n",
    b"                    float horizontalOffset = Vector2.Distance(\r\n",
    b"                        new Vector2(point.x, point.z),\r\n",
    b"                        new Vector2(hit.position.x, hit.position.z));\r\n",
    b"                    if (horizontalOffset > NavMeshHorizontalTolerance)\r\n",
    b"                    {\r\n",
    b"                        failures.Add(\r\n",
    b"                            $\"{enemyLabel} spawn {point} does not stand on the baked NavMesh: \" +\r\n",
    b"                            $\"the nearest navigable floor {hit.position} is \" +\r\n",
    b"                            $\"{horizontalOffset:0.###} units away horizontally.\");\r\n",
    b"                    }\r\n",
    b"                }\r\n",
])

new_inline = b"".join([
    b"                else\r\n",
    b"                {\r\n",
    b"                    string displacement = DescribeHorizontalDisplacement(\r\n",
    b"                        enemyLabel, point, hit.position);\r\n",
    b"                    if (displacement != null)\r\n",
    b"                    {\r\n",
    b"                        failures.Add(displacement);\r\n",
    b"                    }\r\n",
    b"                }\r\n",
])

# 2. The rule itself, next to the other helpers.
rule_anchor = b"        // The builder's own constant rather than a second literal, so a rename can't leave this\r\n"

rule = b"".join([
    b"        // The horizontal half of the placement rule, named so it can be proven directly rather\r\n",
    b"        // than only through whatever the bake happens to produce. A spawn stands on navigable\r\n",
    b"        // floor when the sampled point is essentially underfoot: the sample radius already\r\n",
    b"        // bounds how far away it may be, and this bounds how far to the side. Returns null when\r\n",
    b"        // the placement is good, otherwise the failure to report.\r\n",
    b"        private static string DescribeHorizontalDisplacement(\r\n",
    b"            string enemyLabel,\r\n",
    b"            Vector3 spawn,\r\n",
    b"            Vector3 sampledPosition)\r\n",
    b"        {\r\n",
    b"            float horizontalOffset = Vector2.Distance(\r\n",
    b"                new Vector2(spawn.x, spawn.z),\r\n",
    b"                new Vector2(sampledPosition.x, sampledPosition.z));\r\n",
    b"            if (horizontalOffset <= NavMeshHorizontalTolerance)\r\n",
    b"            {\r\n",
    b"                return null;\r\n",
    b"            }\r\n",
    b"\r\n",
    b"            return $\"{enemyLabel} spawn {spawn} does not stand on the baked NavMesh: the nearest \" +\r\n",
    b"                   $\"navigable floor {sampledPosition} is {horizontalOffset:0.###} units away \" +\r\n",
    b"                   \"horizontally.\";\r\n",
    b"        }\r\n",
    b"\r\n",
])

# 3. Replace the scene-based negative test with one that asserts what actually happens, and add
#    a direct proof of the horizontal rule using the measured Final Room offset.
old_negative_start = b"        // A vertical allowance of half a unit is only safe while the horizontal half of the\r\n"
old_negative_end = b"        private static void CheckSpawnPositions(\r\n"

new_negative = b"".join([
    b"        // A vertical allowance of half a unit is only safe while the check still rejects a point\r\n",
    b"        // that is not standing on navigable floor, so this proves it on the scene rather than\r\n",
    b"        // trusting it: a probe on the Final Room's west wall centre line - a point no spawn array\r\n",
    b"        // contains - must be reported by the very same check the spawns are validated with. The\r\n",
    b"        // bake carves the wall, so what rejects it is the sample radius; the horizontal half is\r\n",
    b"        // proven separately below, because no authored point in this scene happens to sit beside\r\n",
    b"        // a gap narrow enough to exercise it.\r\n",
    b"        [Test]\r\n",
    b"        public void PlacementCheck_RejectsAProbeStandingInARoomWall()\r\n",
    b"        {\r\n",
    b"            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);\r\n",
    b"            try\r\n",
    b"            {\r\n",
    b"                Physics.SyncTransforms();\r\n",
    b"\r\n",
    b"                Vector3 insideWestWall = new Vector3(\r\n",
    b"                    FinalRoomLayout.MinimumX, 0f, FinalRoomLayout.RoomBounds.center.z);\r\n",
    b"                var failures = new List<string>();\r\n",
    b"                CheckSpawnPositions(\"WallProbe\", new[] { insideWestWall }, failures);\r\n",
    b"\r\n",
    b"                Assert.IsTrue(\r\n",
    b"                    failures.Any(failure => failure.Contains(\"baked NavMesh\")),\r\n",
    b"                    \"The placement check must reject a probe standing in a room wall, otherwise \" +\r\n",
    b"                    \"the vertical allowance would let an unnavigable spawn pass. Reported \" +\r\n",
    b"                    $\"instead: {string.Join(\" | \", failures)}\");\r\n",
    b"            }\r\n",
    b"            finally\r\n",
    b"            {\r\n",
    b"                EditorSceneManager.CloseScene(scene, false);\r\n",
    b"            }\r\n",
    b"        }\r\n",
    b"\r\n",
    b"        // The horizontal half, proven on the real numbers this fix was diagnosed from. The\r\n",
    b"        // accepted case is the measured Final Room guard: the bake's sampled surface at\r\n",
    b"        // (8, 0, 74) is 0.136 above the spawn and exactly underfoot, which the old 0.1 radius\r\n",
    b"        // rejected. The rejected case is the same vertical offset displaced sideways, which is\r\n",
    b"        // what a spawn buried in geometry looks like when the floor beyond it is still in range.\r\n",
    b"        [Test]\r\n",
    b"        public void HorizontalRule_AcceptsTheMeasuredFinalRoomOffset_AndRejectsADisplacedSample()\r\n",
    b"        {\r\n",
    b"            Vector3 finalRoomGuard = new Vector3(8f, 0f, 74f);\r\n",
    b"\r\n",
    b"            Assert.IsNull(\r\n",
    b"                DescribeHorizontalDisplacement(\r\n",
    b"                    \"MeleeEnemy\", finalRoomGuard, new Vector3(8f, 0.136f, 74f)),\r\n",
    b"                \"A sampled point directly underfoot must be accepted however far the bake lifts \" +\r\n",
    b"                \"it within the sample radius.\");\r\n",
    b"\r\n",
    b"            string displaced = DescribeHorizontalDisplacement(\r\n",
    b"                \"MeleeEnemy\", finalRoomGuard, new Vector3(8.4f, 0.136f, 74f));\r\n",
    b"            Assert.IsNotNull(\r\n",
    b"                displaced,\r\n",
    b"                \"A sampled point 0.4 units to the side is not floor underfoot and must be \" +\r\n",
    b"                \"rejected, or the vertical allowance would pass a spawn buried in geometry.\");\r\n",
    b"            Assert.That(displaced, Does.Contain(\"0.4\"),\r\n",
    b"                \"The failure must quote the measured displacement so the next reader can see \" +\r\n",
    b"                \"how far off the spawn was.\");\r\n",
    b"        }\r\n",
    b"\r\n",
])

start = data.find(old_negative_start)
end = data.find(old_negative_end)
if start == -1 or end == -1 or end < start:
    print('ABORT: could not bracket the negative test (start=%d end=%d)' % (start, end))
    sys.exit(1)

for name, old in (('inline', old_inline), ('rule anchor', rule_anchor)):
    if data.count(old) != 1:
        print('ABORT: %s found %d times' % (name, data.count(old)))
        sys.exit(1)

data = data[:start] + new_negative + data[end:]
data = data.replace(old_inline, new_inline)
data = data.replace(rule_anchor, rule + rule_anchor)

open(path, 'wb').write(data)
print('patched; bytes=%d lone_lf=%d' % (len(data), data.count(b'\n') - data.count(b'\r\n')))
