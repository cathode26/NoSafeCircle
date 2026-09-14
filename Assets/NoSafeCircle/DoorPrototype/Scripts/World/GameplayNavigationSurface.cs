using Unity.AI.Navigation;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.World
{
    // NSC-089 AC-002: the runtime owner of the shared Unity AI Navigation NavMeshSurface used to
    // bake the walkable gameplay NavMesh from composed room collision geometry. Enemy movement
    // and the test-owned NavMeshAgent both navigate using the same project-configured agent type
    // this component bakes with, so their radius/height/slope always match the baked surface.
    [RequireComponent(typeof(NavMeshSurface))]
    public sealed class GameplayNavigationSurface : MonoBehaviour
    {
        private NavMeshSurface surface;

        public NavMeshSurface Surface
        {
            get
            {
                EnsureSurface();
                return surface;
            }
        }

        // Configures the surface to read gameplay collision colliders only - never the
        // visual-only Tilemap renderers, which carry no collider - using the project's single
        // configured NavMesh agent type, so the baked radius/height/slope always match that
        // shared ProjectSettings profile rather than a value duplicated here. Then bakes the
        // walkable NavMesh immediately.
        public void ConfigureAndBuild()
        {
            EnsureSurface();
            surface.agentTypeID = NavMesh.GetSettingsByIndex(0).agentTypeID;
            surface.collectObjects = CollectObjects.All;
            surface.useGeometry = NavMeshCollectGeometry.PhysicsColliders;
            surface.BuildNavMesh();
        }

        // Unregisters this instance's previously baked NavMesh from the active navigation system
        // before its owning GameObject is destroyed and rebuilt, so a rebuilt scene never leaves
        // a stale NavMesh registered alongside the newly baked one.
        public void ClearBakedData()
        {
            EnsureSurface();
            surface.RemoveData();
        }

        private void EnsureSurface()
        {
            if (surface == null)
            {
                surface = GetComponent<NavMeshSurface>();
            }
        }
    }
}
