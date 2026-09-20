"""Add the negative proof for the placement check (CRLF-preserving, byte level)."""
import sys

path = sys.argv[1]
data = open(path, 'rb').read()

old_using = b"using NoSafeCircle.DoorPrototype.Editor.World;\r\n"
new_using = (b"using NoSafeCircle.DoorPrototype.Editor.World;\r\n"
             b"using NoSafeCircle.DoorPrototype.World.Rooms;\r\n")

anchor = b"        private static void CheckSpawnPositions(\r\n"

negative_test = b"".join([
    b"        // A vertical allowance of half a unit is only safe while the horizontal half of the\r\n",
    b"        // check still rejects a point that is not standing on navigable floor, so this proves\r\n",
    b"        // the guard rather than trusting it: a probe placed on the Final Room's west wall\r\n",
    b"        // centre line - a point no spawn array contains - must be reported by the very same\r\n",
    b"        // check the spawns are validated with.\r\n",
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
    b"                    failures.Any(failure => failure.Contains(\"does not stand on the baked NavMesh\")),\r\n",
    b"                    \"The horizontal half of the placement check must reject a probe standing in \" +\r\n",
    b"                    \"a room wall, otherwise the vertical allowance would let a displaced spawn \" +\r\n",
    b"                    $\"pass. Reported instead: {string.Join(\" | \", failures)}\");\r\n",
    b"            }\r\n",
    b"            finally\r\n",
    b"            {\r\n",
    b"                EditorSceneManager.CloseScene(scene, false);\r\n",
    b"            }\r\n",
    b"        }\r\n",
    b"\r\n",
])

for name, old in (('using', old_using), ('anchor', anchor)):
    if data.count(old) != 1:
        print('ABORT: {0} anchor found {1} times'.format(name, data.count(old)))
        sys.exit(1)

data = data.replace(old_using, new_using).replace(anchor, negative_test + anchor)
open(path, 'wb').write(data)
print('patched; bytes={0} lone_lf={1}'.format(len(data), data.count(b'\n') - data.count(b'\r\n')))
