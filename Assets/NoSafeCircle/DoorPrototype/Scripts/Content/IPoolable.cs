namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// What a pooled component restores on the way out and on the way back in. ENGINEERING_STANDARDS 9.3.
    /// </summary>
    /// <remarks>
    /// 9.3, verbatim on the point that matters: "A simple inactive flag is insufficient." The pool sets
    /// the active flag and the parent; EVERYTHING ELSE is the component's job, and 9.3 lists it -
    /// velocities and physics state, animation state, particles, materials and property blocks,
    /// sorting and masks, callbacks and subscriptions, timers and coroutines, gameplay data, and child
    /// objects created during use. A component that restores only what it remembers to restore is
    /// the classic pooling bug: the second enemy out of the pool is still dying.
    /// </remarks>
    public interface IPoolable
    {
        /// <summary>Called after the instance is active and parented for use. Put every piece of
        /// semantic state back to "fresh from the prefab".</summary>
        void OnCheckout();

        /// <summary>Called while the instance is still active, before it is deactivated and stored.
        /// Stop what is running, unsubscribe, drop references, destroy children made during use.</summary>
        void OnReturn();
    }

    /// <summary>What a pool does with a checkout that arrives at its maximum capacity. 9.2's "overflow
    /// policy", made a choice the owner declares rather than a behaviour it discovers.</summary>
    public enum PoolOverflowPolicy
    {
        /// <summary>Refuse it: <c>TryCheckout</c> returns false and the refusal is counted.</summary>
        Reject = 0,

        /// <summary>Grow past the maximum and count the growth, so the ceiling is a diagnostic rather
        /// than a wall.</summary>
        Expand = 1
    }
}
