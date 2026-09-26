using System.Threading;
using System.Threading.Tasks;

namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>
    /// A spawner that needs content resident before its phase runs. Optional, and additive to
    /// <see cref="ISpawner"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS EXISTS BECAUSE THE DOCUMENTATION PROMISED IT AND THE CODE DID NOT DELIVER IT. ISpawner's
    /// own remarks said "everything a spawner needs is resident before its phase runs, because the
    /// bootstrap awaits a preload pass first" - and there was no preload pass. An adversarial review
    /// of Increment A found it before any family lane had committed, which is the only reason this
    /// is one file instead of seven rewrites.
    /// </para>
    /// <para>
    /// WHY THE PROMISE MATTERS RATHER THAN BEING TIDINESS: ENGINEERING_STANDARDS 7.2 forbids
    /// blocking the main thread for content AND forbids Addressables <c>WaitForCompletion</c> in
    /// WebGL game code. Those two together mean a spawner CANNOT legally wait for an asset inside
    /// <see cref="ISpawner.Spawn"/>. If loading happens inside the synchronous placement loop - which
    /// is what <c>PropSpawner</c> does today with <c>Resources.Load</c>, legally, because Resources
    /// is synchronous - then the move to Addressables has no correct form at all. The seam has to
    /// exist BEFORE the lanes are written, or every lane encodes the shape that cannot migrate.
    /// </para>
    /// <para>
    /// IT IS A SEPARATE INTERFACE, NOT A METHOD ON ISpawner, ON PURPOSE. Seven workers are building
    /// against ISpawner at this moment. Adding a member to it would break all seven mid-flight;
    /// adding an interface they may choose to implement breaks none, and a spawner with no
    /// asynchronous content - the navigation bake, for instance - correctly implements nothing.
    /// </para>
    /// <para>
    /// THE CONTRACT: when <see cref="PreloadAsync"/> completes, everything this spawner will ask for
    /// during <see cref="ISpawner.Spawn"/> can be fetched synchronously. Register what you load with
    /// an <c>AssetScope</c> so the ownership is visible (standard 8.5); do not hold a handle nobody
    /// can find.
    /// </para>
    /// </remarks>
    public interface IContentPreloader
    {
        /// <summary>
        /// Makes this spawner's content resident. Awaited by the bootstrap before ANY phase runs, so
        /// it may not assume another lane has spawned yet.
        /// </summary>
        /// <param name="cancellationToken">
        /// Cancelled when the build is abandoned. Standard 7.2: any operation that can outlive its
        /// caller accepts cancellation.
        /// </param>
        Task PreloadAsync(CancellationToken cancellationToken);
    }
}
