using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.World;
using Unity.AI.Navigation;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.Navigation
{
    // The rule every phase after Navigation must carry, stated once in code so nobody restates it
    // from memory: a solid collider that is alive during a re-bake is baked around unless a
    // NavMeshModifier with ignoreFromBuild covers it. The first bake is correct by phase order. A
    // re-bake (BuildWorld twice) runs Navigation(2) before Doors(3), Player(4), Enemies(5) and
    // Hud(6) have cleared their previous output, so their objects are still alive and any collider
    // among them becomes a wall in the new surface. The Navigation lane cannot edit those lanes'
    // prefabs; what it can do is answer "would my bake collect this?" from the same rules the bake
    // uses, so a fixture, the integrator, or NavigationSpawner itself can name a violator.
    //
    // WHAT THE BAKE ACTUALLY DOES, read from com.unity.ai.navigation 2.0.14 rather than recalled:
    // NavMeshSurface.CollectSources turns every active NavMeshModifier into a NavMeshBuildMarkup
    // {root, ignoreFromBuild, applyToChildren} (Runtime/NavMeshSurface.cs:396-411), then removes
    // any source whose GameObject carries a NavMeshAgent or a NavMeshObstacle, because
    // ignoreNavMeshAgent and ignoreNavMeshObstacle default to true (:75, :78, :438-444) and
    // GameplayNavigationSurface leaves them there. The modifier's own remark: it "overrides the
    // properties set to this GameObject by any other NavMeshModifier in the parent hierarchy", so
    // the NEAREST modifier decides.
    public static class NavMeshRebakeExclusion
    {
        /// <summary>
        /// Marks a runtime-created object the way a later lane's prefab must be marked: a
        /// NavMeshModifier with ignoreFromBuild on the root, applied to its children. Idempotent.
        /// Returns nothing on purpose: the modifier's type lives in the Unity.AI.Navigation
        /// assembly, which only the runtime assembly references (NSC-089 AC-002), and a test
        /// assembly could not name a returned value of that type.
        /// </summary>
        public static void Apply(GameObject target)
        {
            var modifier = target.GetComponent<NavMeshModifier>();
            if (modifier == null)
            {
                modifier = target.AddComponent<NavMeshModifier>();
            }

            modifier.ignoreFromBuild = true;
            modifier.applyToChildren = true;
        }

        /// <summary>True when the bake NavigationSpawner runs would skip this collider.</summary>
        public static bool Excludes(Collider collider)
        {
            GameObject owner = collider.gameObject;
            if (owner.GetComponent<NavMeshAgent>() != null || owner.GetComponent<NavMeshObstacle>() != null)
            {
                return true;
            }

            // The nearest active modifier decides. On the collider's own object ignoreFromBuild is
            // enough; on an ancestor it must also apply to children. An ancestor that declines to
            // apply to children ENDS the search rather than letting a farther ancestor reach past
            // it - the conservative reading, which can only ever over-report, never hide a wall.
            int agentTypeID = NavMesh.GetSettingsByIndex(0).agentTypeID;
            for (Transform current = collider.transform; current != null; current = current.parent)
            {
                var modifier = current.GetComponent<NavMeshModifier>();
                if (modifier == null || !modifier.isActiveAndEnabled || !modifier.AffectsAgentType(agentTypeID))
                {
                    continue;
                }

                bool onTheColliderItself = current == collider.transform;
                return modifier.ignoreFromBuild && (onTheColliderItself || modifier.applyToChildren);
            }

            return false;
        }

        /// <summary>
        /// Every enabled, non-trigger collider on an active object under root that the bake would
        /// collect. Empty means root can be left alive through a re-bake without changing the
        /// surface, which is the property rule 5 asks of every later lane's prefab.
        /// </summary>
        public static List<Collider> FindCollected(Transform root)
        {
            var collected = new List<Collider>();
            foreach (Collider collider in root.GetComponentsInChildren<Collider>(false))
            {
                if (collider.enabled && !collider.isTrigger && !Excludes(collider))
                {
                    collected.Add(collider);
                }
            }

            return collected;
        }

        /// <summary>
        /// The population the rule governs: the colliders under every spawner whose phase is later
        /// than Navigation, found from the object the spawners are parented to (GameBootstrap
        /// instantiates them as its children).
        /// </summary>
        public static List<Collider> FindCollectedUnderLaterPhases(Transform bootstrapRoot)
        {
            var collected = new List<Collider>();
            foreach (ISpawner spawner in bootstrapRoot.GetComponentsInChildren<ISpawner>(true))
            {
                var component = spawner as Component;
                if (component == null || spawner.Phase <= SpawnPhase.Navigation)
                {
                    continue;
                }

                collected.AddRange(FindCollected(component.transform));
            }

            return collected;
        }

        /// <summary>"GameManagers/DoorSpawner/Door/DoorVisual" - the name a log line needs.</summary>
        public static string HierarchyPath(Transform target)
        {
            string path = target.name;
            for (Transform parent = target.parent; parent != null; parent = parent.parent)
            {
                path = parent.name + "/" + path;
            }

            return path;
        }
    }
}
