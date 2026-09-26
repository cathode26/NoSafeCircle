namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>
    /// One family of the world, instantiated at Play from authored prefabs and authored data.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS INTERFACE IS THE WHOLE PARALLELISM STORY. Vincent, 2026-09-26: "we can have multiple
    /// instances of unity, where each agent can work in one, create prefabs (not touch the scene)
    /// then write code to instantiate them with their own component." A lane owner writes ONE class
    /// that implements this, ships it with its own prefabs and its own PlayMode fixture, and never
    /// opens a file another lane owns. <see cref="GameBootstrap"/> finds it by component and runs it
    /// in <see cref="Phase"/> order.
    /// </para>
    /// <para>
    /// SPAWN IS SYNCHRONOUS ON PURPOSE, AND THIS IS THE ONE RULE NOT TO "IMPROVE". Content loading is
    /// asynchronous; PLACEMENT is not. Everything a spawner needs is resident before its phase runs,
    /// because the bootstrap awaits a preload pass first. That is what keeps ENGINEERING_STANDARDS
    /// 7.2 satisfiable - "Do not use Addressables WaitForCompletion in WebGL-targeted game code" and
    /// "Do not block the main thread waiting for asynchronous content". An async Spawn would push
    /// every lane into deciding for itself how to wait, and one of them would reach for
    /// WaitForCompletion. Making the signature synchronous removes the question.
    /// </para>
    /// <para>
    /// A SPAWNER IS ALSO ALLOWED TO BE RE-RUN. Spawn clears whatever its previous call created before
    /// creating anything, so a test can call it twice and a reload does not double the world. The
    /// five editor dressing builders lacked exactly this and each re-bake appended.
    /// </para>
    /// </remarks>
    public interface ISpawner
    {
        /// <summary>When this spawner runs relative to the other families.</summary>
        SpawnPhase Phase { get; }

        /// <summary>
        /// Creates this family's objects and returns how many it created. Zero is a legitimate answer
        /// for a family with nothing authored yet; a failure throws or logs rather than returning a
        /// count that lies about what happened.
        /// </summary>
        int Spawn();
    }
}
