using System;
using System.Threading;
using System.Threading.Tasks;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>One package load, before it becomes a lease owned by the caller.</summary>
    internal interface IAddressableAssetOperation<T> where T : UnityEngine.Object
    {
        bool Succeeded { get; }
        T Result { get; }
        Exception OperationException { get; }

        /// <summary>False transfers release responsibility to the operation: release when the
        /// cancelled load finishes. True leaves release responsibility with the service.</summary>
        Task<bool> WhenDoneOrCancelled(CancellationToken cancellation);

        void Release();
    }
}
