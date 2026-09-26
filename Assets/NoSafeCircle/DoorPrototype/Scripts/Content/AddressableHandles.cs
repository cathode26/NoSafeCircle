using System.Threading;
using System.Threading.Tasks;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// The one place an Addressables handle is turned into something awaitable. Main thread only,
    /// completion event only, and never <c>handle.Task</c> or <c>WaitForCompletion</c>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS GAME SHIPS TO WEBGL, AND THE PACKAGE'S OWN MANUAL RULES OUT THE OBVIOUS ROUTE. Addressables
    /// 2.3.16, <c>Documentation~/AddressableAssetsAsyncOperationHandle.md:74</c>: "The
    /// AsyncOperationHandle.Task property isn't available on the WebGL platform, which doesn't support
    /// multitasking." And ENGINEERING_STANDARDS 7.2 forbids <c>WaitForCompletion</c> in WebGL-targeted
    /// game code outright - the same manual explains that on WebGL the tight loop it spins blocks the
    /// web request it is waiting for, forever. So every await in this layer goes through the
    /// <see cref="AsyncOperationHandle{TObject}.Completed"/> event into a plain
    /// <see cref="TaskCompletionSource{TResult}"/>, which needs no thread and no scheduler: the event
    /// fires on the main thread and the continuation runs there.
    /// </para>
    /// <para>
    /// ORDER MATTERS IN <see cref="WhenDone{T}"/>: it reads <c>IsDone</c> BEFORE subscribing. A handle
    /// that is already complete still delivers <c>Completed</c> (the package defers it to LateUpdate),
    /// but returning a finished task directly is cheaper and, in an EditMode test with no player loop,
    /// the only version that ever completes. There is no race between the check and the subscription
    /// because both happen on the one thread that can complete the operation.
    /// </para>
    /// </remarks>
    internal static class AddressableHandles
    {
        /// <summary>Completes with the handle once the operation is done. Never throws for a failed
        /// operation; read <c>Status</c> and <c>OperationException</c> afterwards.</summary>
        public static Task<AsyncOperationHandle<T>> WhenDone<T>(AsyncOperationHandle<T> handle)
        {
            if (handle.IsDone)
            {
                return Task.FromResult(handle);
            }

            var completion = new TaskCompletionSource<AsyncOperationHandle<T>>();
            handle.Completed += done => completion.TrySetResult(done);
            return completion.Task;
        }

        /// <summary>
        /// True when the operation finished; false when <paramref name="cancellation"/> fired first.
        /// Addressables cannot abort a load in flight, so on cancellation the handle is left to finish
        /// and is released the moment it does - the caller must NOT touch it again. That keeps
        /// STANDARDS 8.5's "mirror every load with a release" true even for a load nobody waited for.
        /// </summary>
        public static async Task<bool> WhenDoneOrCancelled<T>(AsyncOperationHandle<T> handle,
            CancellationToken cancellation)
        {
            Task<AsyncOperationHandle<T>> done = WhenDone(handle);
            if (!cancellation.CanBeCanceled || done.IsCompleted)
            {
                await done;
                return true;
            }

            var cancelled = new TaskCompletionSource<bool>();
            using (cancellation.Register(() => cancelled.TrySetResult(true)))
            {
                Task first = await Task.WhenAny(done, cancelled.Task);
                if (first == done)
                {
                    return true;
                }
            }

            handle.Completed += finished => Addressables.Release(finished);
            return false;
        }
    }
}
