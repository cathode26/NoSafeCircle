using Unity.AI.Navigation;
using UnityEngine;
using UnityEngine.AI;

namespace NoSafeCircle.DoorPrototype.Enemies.Pooling
{
    /// <summary>
    /// The ENGINEERING_STANDARDS 9.3 poolable contract for an enemy root: every reset seam the
    /// enemy components already expose, called from one place, so the pool never needs to know
    /// which components a prefab carries. A reference left empty in the prefab resolves once by
    /// GetComponent in Awake; a component the prefab does not have stays null and is skipped, so
    /// the fuller NSC-055/NSC-125 prefabs drop in later without a change here.
    /// </summary>
    /// <remarks>
    /// <para>9.3's list, item by item, and where each is satisfied:</para>
    /// <code>
    ///   active state              the pool deactivates; EncounterAdmissionController activates
    ///   transform and parent      OnCheckout re-applies the slot pose; the parent never changes
    ///   velocities / physics      OnReturn: ResetPath + velocity zero on the agent
    ///   animation state           EnemyAnimationController.OnEnable nulls its current state, so
    ///                             re-activation re-selects idle; the Animator itself resets on
    ///                             disable (m_KeepAnimatorStateOnDisable is 0 in the prefab)
    ///   particles                 none exist on these prefabs
    ///   materials / property blocks  EnemyHoverHighlight clears its block in OnDisable (not on
    ///                             today's prefab; covered when it arrives)
    ///   sorting and masks         prefab literals, never written at runtime
    ///   callbacks / subscriptions EnemySpawner adds and removes the Defeated handler;
    ///                             EnemyLockedDoorAttack releases its door in OnDisable
    ///   timers / coroutines       the Reset* seams; no coroutine exists in these components
    ///   gameplay data             ResetHealth, ResetTargetKnowledge, ResetStatusEffects, ResetAttack x3
    ///   child objects created during use  THE WRAITH'S WISPS ARE NOT CHILDREN, and
    ///                             EnemyLanternWispCaster has no public clear - only its OnDestroy
    ///                             removes them, and its mana and cooldown have no reset either -
    ///                             so the wraith pool destroys on return (EnemySpawner passes
    ///                             recycleOnReturn: false) until that component grows a seam
    /// </code>
    /// </remarks>
    [DisallowMultipleComponent]
    public sealed class EnemyPoolable : MonoBehaviour, IEnemyPoolable
    {
        [SerializeField] private EnemyHealth health;
        [SerializeField] private EnemyTargetKnowledge targetKnowledge;
        [SerializeField] private EnemyPursuitMovement pursuit;
        [SerializeField] private NavMeshAgent agent;
        [SerializeField] private EnemyStatusEffectMovement statusEffects;
        [SerializeField] private MeleeEnemyAttack meleeAttack;
        [SerializeField] private EnemyLockedDoorAttack lockedDoorAttack;
        [SerializeField] private RangedEnemyAttack rangedAttack;

        private void Awake()
        {
            if (health == null) health = GetComponent<EnemyHealth>();
            if (targetKnowledge == null) targetKnowledge = GetComponent<EnemyTargetKnowledge>();
            if (pursuit == null) pursuit = GetComponent<EnemyPursuitMovement>();
            if (agent == null) agent = GetComponent<NavMeshAgent>();
            if (statusEffects == null) statusEffects = GetComponent<EnemyStatusEffectMovement>();
            if (meleeAttack == null) meleeAttack = GetComponent<MeleeEnemyAttack>();
            if (lockedDoorAttack == null) lockedDoorAttack = GetComponent<EnemyLockedDoorAttack>();
            if (rangedAttack == null) rangedAttack = GetComponent<RangedEnemyAttack>();
            EnsureNavMeshExclusion();
        }

        // ENEMIES SPAWN AT PHASE 5, AFTER NAVIGATION BAKES AT PHASE 2. The first bake is correct
        // by phase order, but a rebuild (BuildWorld twice, or a reload in the same session) re-bakes
        // while the previous enemies are still alive for one frame, and a NavMeshSurface set to
        // collect PhysicsColliders would fold any collider they carry into the walkable surface as
        // static geometry. NavMeshModifier { ignoreFromBuild } is the Unity-native way to exclude
        // them. Today's enemies carry no collider; NSC-125's body collider is what this protects.
        //
        // WHY IT IS ADDED HERE AND NOT WRITTEN INTO THE PREFAB YAML: Tools/prefab_lint.py resolves
        // every m_Script guid against the .meta files under Assets/ only, and NavMeshModifier's
        // guid lives in the com.unity.ai.navigation package cache, so a prefab that references it
        // fails the lint the branch is required to pass. Measured 2026-09-26: the guid index holds
        // 1376 guids and the package guid is not among them. Awake runs exactly once per instance,
        // at creation - the pool's "creation method" - so this is the same moment the prefab would
        // have supplied it. Move it into the YAML the day the lint indexes package guids.
        private void EnsureNavMeshExclusion()
        {
            NavMeshModifier modifier = GetComponent<NavMeshModifier>();
            if (modifier == null) modifier = gameObject.AddComponent<NavMeshModifier>();
            modifier.ignoreFromBuild = true;
            modifier.applyToChildren = true;
        }

        public void OnCheckout(Pose spawnPose)
        {
            // Equal to the Awake pose by construction; re-applied so a slot that was moved by
            // gameplay and returned while off the navmesh still starts exactly where it belongs.
            transform.SetPositionAndRotation(spawnPose.position, spawnPose.rotation);
            if (health != null) health.ResetHealth();
            if (targetKnowledge != null) targetKnowledge.ResetTargetKnowledge();
            if (statusEffects != null) statusEffects.ResetStatusEffects();
            ResetAttacks();
        }

        public void OnReturn()
        {
            // ResetPursuit clears the path and warps to the Awake pose itself; it needs the agent
            // active and on the navmesh, which is why the pool calls this BEFORE deactivating.
            if (pursuit != null) pursuit.ResetPursuit();
            if (targetKnowledge != null) targetKnowledge.ResetTargetKnowledge();
            if (statusEffects != null) statusEffects.ResetStatusEffects();
            ResetAttacks();
            if (agent != null && agent.isOnNavMesh)
            {
                agent.ResetPath();
                agent.velocity = Vector3.zero;
            }
        }

        private void ResetAttacks()
        {
            if (meleeAttack != null) meleeAttack.ResetAttack();
            if (lockedDoorAttack != null) lockedDoorAttack.ResetAttack();
            if (rangedAttack != null) rangedAttack.ResetAttack();
        }
    }
}
