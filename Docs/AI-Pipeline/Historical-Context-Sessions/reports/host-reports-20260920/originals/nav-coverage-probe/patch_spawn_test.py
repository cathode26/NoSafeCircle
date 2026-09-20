"""Patch EnemySpawnPlacementTests' NavMesh tolerance premise (CRLF-preserving, byte level)."""
import sys

path = sys.argv[1]
data = open(path, 'rb').read()

old_const = b"        private const float NavMeshSampleTolerance = 0.1f;\r\n"

new_const = b"".join([
    b"        // The bake's own vertical error, not a slackened gate. NavMesh.SamplePosition returns\r\n",
    b"        // a point on the baked surface, and voxelization lifts that surface away from the\r\n",
    b"        // nominal 0.083 agent offset near raised geometry. Measured in the committed scene\r\n",
    b"        // (2026-09-17): every other room is flat at 0.083, while the Final Room rises from\r\n",
    b"        // 0.083 on its centre line to 0.156 beside its benches. An absolute 3D tolerance of\r\n",
    b"        // 0.1 therefore rejected the two Final Room guards at (8, 0, 74) and (-8, 0, 77) even\r\n",
    b"        // though that room's FloorCollision sits directly under both with zero horizontal\r\n",
    b"        // displacement. What the design actually requires - navigable floor underfoot - is a\r\n",
    b"        // generous vertical allowance plus a strict horizontal one.\r\n",
    b"        private const float NavMeshVerticalTolerance = 0.5f;\r\n",
    b"        private const float NavMeshHorizontalTolerance = 0.05f;\r\n",
])

old_check = b"".join([
    b"                if (!NavMesh.SamplePosition(point, out NavMeshHit hit, NavMeshSampleTolerance, NavMesh.AllAreas))\r\n",
    b"                {\r\n",
    b"                    failures.Add(\r\n",
    b"                        $\"{enemyLabel} spawn {point} did not sample onto the baked NavMesh within \" +\r\n",
    b"                        $\"{NavMeshSampleTolerance} units.\");\r\n",
    b"                }\r\n",
])

new_check = b"".join([
    b"                if (!NavMesh.SamplePosition(point, out NavMeshHit hit, NavMeshVerticalTolerance, NavMesh.AllAreas))\r\n",
    b"                {\r\n",
    b"                    failures.Add(\r\n",
    b"                        $\"{enemyLabel} spawn {point} found no baked NavMesh within \" +\r\n",
    b"                        $\"{NavMeshVerticalTolerance} units: nothing navigable underfoot.\");\r\n",
    b"                }\r\n",
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

for name, old in (('const', old_const), ('check', old_check)):
    if data.count(old) != 1:
        print('ABORT: {0} anchor found {1} times'.format(name, data.count(old)))
        sys.exit(1)

data = data.replace(old_const, new_const).replace(old_check, new_check)
open(path, 'wb').write(data)
print('patched; bytes={0} lone_lf={1} crlf={2}'.format(
    len(data), data.count(b'\n') - data.count(b'\r\n'), data.count(b'\r\n')))
