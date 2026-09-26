using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies.Pooling
{
    /// <summary>
    /// The reset contract a pooled enemy root implements. ENGINEERING_STANDARDS 9.3: a pooled
    /// object restores ALL of its semantic state, and "a simple inactive flag is insufficient".
    /// </summary>
    /// <remarks>
    /// <para>
    /// NAMED IEnemyPoolable, NOT IPoolable, ON PURPOSE. The Content lane ships
    /// <c>NoSafeCircle.DoorPrototype.Content.IPoolable</c> (an <c>OnCheckout()</c> with no pose)
    /// for its Addressables pool. Two types called IPoolable imported side by side are ambiguous
    /// in any file that uses both namespaces - and <see cref="EnemyPrefabPool"/> uses Content for
    /// <c>AssetLease</c>. A distinct name costs nothing and removes a compile error on the
    /// combined tree.
    /// </para>
    /// <para>
    /// THE POSE IS AN ARGUMENT BECAUSE A SLOT IS A SPAWN POINT. The pool hands the instance the
    /// exact pose it was created at, so the checkout reset can re-apply it without the pool
    /// touching the transform itself.
    /// </para>
    /// </remarks>
    public interface IEnemyPoolable
    {
        /// <summary>
        /// Called by the pool before the instance is handed out, while the instance is still
        /// INACTIVE. Restores the floor-initial state at the slot's pose. Activation is not this
        /// method's job: the encounter admission controller decides when an enemy becomes active.
        /// </summary>
        void OnCheckout(Pose spawnPose);

        /// <summary>
        /// Called by the pool when the instance comes back, while the instance is still ACTIVE
        /// (so agent and path calls are legal). Clears everything gameplay changed so the next
        /// checkout starts clean; the pool deactivates the instance immediately afterwards.
        /// </summary>
        void OnReturn();
    }
}
