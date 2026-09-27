using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using UnityEngine.AddressableAssets.ResourceLocators;
using UnityEngine.ResourceManagement.ResourceLocations;

[assembly: InternalsVisibleTo("NoSafeCircle.DoorPrototype.Tests.Editor")]

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>The package boundary. Tests supply in-memory locators and controlled load operations.</summary>
    internal interface IAddressableAssetOperations
    {
        IEnumerable<IResourceLocator> ResourceLocators { get; }

        Task EnsureInitializedAsync();

        IAddressableAssetOperation<T> LoadAssetAsync<T>(IResourceLocation location) where T : UnityEngine.Object;
    }
}
