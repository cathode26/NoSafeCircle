using System;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.AddressableAssets.ResourceLocators;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// Initializes Addressables once and exposes the result as something to AWAIT, not a bool to poll.
    /// </summary>
    /// <remarks>
    /// <para>
    /// ENGINEERING_STANDARDS 7.2: "Do not expose initialization as a bool that every consumer polls.
    /// Await initialization once through a bootstrap/readiness operation." That one place is
    /// <c>GameBootstrap</c>: it awaits <see cref="EnsureInitializedAsync"/>, then preloads, then runs
    /// the spawners synchronously - so a spawner never asks whether content has arrived, because by
    /// the time it runs the answer is yes by construction. There is deliberately no
    /// <c>IsInitialized</c> here. Vincent's slot engine exposed one (<c>public bool isInitialized</c>
    /// set from an <c>async void Start</c>) and SlotEngineGemReview 05 lists that shape under
    /// sediment: "initialization exposed as a bool that callers poll every frame".
    /// </para>
    /// <para>
    /// EVERY CALLER GETS THE SAME TASK, so a hundred awaiters cost one initialization, and a failed one
    /// is retried by the next caller rather than cached forever - in the Editor the usual cause is
    /// that nobody has run the settings setup yet, and the fix is one menu item away.
    /// </para>
    /// <para>
    /// THE HANDLE IS RELEASED HERE, ONCE, WHICH IS EXACTLY WHAT THE DEFAULT OVERLOAD DOES ITSELF:
    /// <c>Addressables.InitializeAsync()</c> auto-releases on completion, which would make the handle
    /// unsafe to inspect afterwards, so this asks for the manual variant and releases in
    /// <c>finally</c>. A second <c>InitializeAsync</c> call after that release returns a completed
    /// operation (<c>AddressablesImpl.cs:357-365</c>), which is why re-initialization is harmless.
    /// </para>
    /// </remarks>
    public static class AddressablesInitialization
    {
        private static Task ready;

        /// <summary>The readiness boundary. Await it; it completes when content can be loaded and
        /// faults with <see cref="ContentInitializationException"/> when it cannot.</summary>
        public static Task EnsureInitializedAsync()
        {
            if (ready == null || ready.IsFaulted)
            {
                ready = InitializeAsync();
            }

            return ready;
        }

        private static async Task InitializeAsync()
        {
            AsyncOperationHandle<IResourceLocator> handle = Addressables.InitializeAsync(false);
            try
            {
                await AddressableHandles.WhenDone(handle);
                if (handle.Status != AsyncOperationStatus.Succeeded)
                {
                    string reason = handle.OperationException?.Message ?? "no exception was reported";
                    throw new ContentInitializationException(
                        "Addressables failed to initialize, so no content can load. In the Editor, run "
                        + "'No Safe Circle/Content/Create Addressables Settings And Groups' once; in a "
                        + "player, the content build is missing or broken. Reason: " + reason,
                        handle.OperationException);
                }
            }
            finally
            {
                Addressables.Release(handle);
            }
        }

        // With "Enter Play Mode Options" set to skip the domain reload, statics survive between play
        // sessions; this is Unity's documented hook for resetting them. With a normal reload it is a no-op.
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetForNewPlaySession()
        {
            ready = null;
        }
    }

    /// <summary>Content cannot be loaded at all. Fatal; there is nothing a caller can fall back to.</summary>
    public sealed class ContentInitializationException : Exception
    {
        public ContentInitializationException(string message, Exception inner)
            : base(message, inner)
        {
        }
    }
}
