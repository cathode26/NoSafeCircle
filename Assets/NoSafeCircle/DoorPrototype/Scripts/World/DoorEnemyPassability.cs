using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.World
{
    // NSC-090 AC-001: the semantic door state Door and Interaction (DoorInteractable) supplies to
    // this component's public SetDoorState method. Sealed and locked block enemy NavMesh
    // traversal through the doorway; open and broken permit it. DoorEnemyPassability owns this
    // translation - it never reads or changes DoorInteractable's own state.
    public enum DoorPassabilityState
    {
        Sealed,
        Open,
        Locked,
        Broken
    }

    // NSC-090 AC-002: the navigation-owned door-passability component. Owns a single NavMesh
    // obstacle sized to the doorway opening and carves a hole across it in the walkable NavMesh
    // that GameplayNavigationSurface (NSC-089) already baked. Sealed/locked enable carving so no
    // enemy path can cross the doorway; open/broken disable carving so the doorway remains part
    // of the already-baked walkable floor. SetDoorState is the only entry point that may change
    // the owned NavMeshObstacle - DoorInteractable, enemy pursuit code, and every other caller
    // must go through it instead of touching the obstacle directly.
    [DisallowMultipleComponent]
    [RequireComponent(typeof(NavMeshObstacle))]
    public sealed class DoorEnemyPassability : MonoBehaviour
    {
        // Local-space box covering the doorway opening the owned obstacle carves across.
        // DoorPrototypeSceneBuilder/NSC-051 may override these per door instance to match
        // authored doorway geometry; the defaults assume a 3-unit-wide opening centered on this
        // component's own transform, mirroring DoorAnchorMarker's default OpeningWidth.
        [SerializeField] private Vector3 obstacleCenter = Vector3.zero;
        [SerializeField] private Vector3 obstacleSize = new Vector3(3f, 3f, 1f);

        private NavMeshObstacle obstacle;

        /// The most recently published semantic door state. Defaults to Sealed so a door that has
        /// never received a state yet blocks enemy traversal rather than silently permitting it.
        public DoorPassabilityState CurrentState { get; private set; } = DoorPassabilityState.Sealed;

        private void Awake()
        {
            EnsureObstacle();
        }

        /// AC-001: translates Door and Interaction's semantic door state into enemy NavMesh
        /// traversal through this doorway. Sealed and locked carve a blocking hole across the
        /// opening; open and broken remove that hole so the doorway is walkable again.
        public void SetDoorState(DoorPassabilityState state)
        {
            EnsureObstacle();
            CurrentState = state;
            obstacle.carving = IsBlocking(state);
        }

        private static bool IsBlocking(DoorPassabilityState state)
        {
            return state == DoorPassabilityState.Sealed || state == DoorPassabilityState.Locked;
        }

        private void EnsureObstacle()
        {
            if (obstacle != null) return;

            obstacle = GetComponent<NavMeshObstacle>();
            obstacle.shape = NavMeshObstacleShape.Box;
            obstacle.center = obstacleCenter;
            obstacle.size = obstacleSize;
            // The doorway obstacle never moves, so a one-shot stationary carve is sufficient and
            // avoids the added per-frame carving cost of a moving obstacle.
            obstacle.carveOnlyStationary = true;
            obstacle.carving = IsBlocking(CurrentState);
        }
    }
}
