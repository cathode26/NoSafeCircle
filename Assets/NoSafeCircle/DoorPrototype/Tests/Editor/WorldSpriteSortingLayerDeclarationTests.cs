using System.Linq;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>
    /// The project declares the sorting layer every world sprite draws on.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THIS EXISTS BECAUSE THE ONLY CODE THAT CHECKED IT IS BEING DELETED. The check lived in
    /// Editor/DoorPrototypeSceneBuilder.cs, ValidateWorldSpriteSortingLayerDeclared, which ran as a
    /// side effect of building the old composed scene. When the old world goes, nothing in the
    /// project verifies that ProjectSettings/TagManager.asset still declares the layer - and a
    /// project setting is not in any assembly, so no compile error and no missing reference would
    /// announce its loss. It would surface as sprites silently drawing in the wrong order.
    /// </para>
    /// <para>
    /// IT ASSERTS THE RELATION RATHER THAN THE NUMBER. The old check captured the layer's id, and
    /// TagManager.asset currently gives WorldSprites uniqueID 1043912875 - but that value is
    /// arbitrary and pinning it would fail on any harmless re-save while proving nothing about
    /// rendering. What actually decides draw order is the layer's INDEX in SortingLayer.layers,
    /// compared BEFORE sortingOrder, which is the rule Scripts/World/WorldSpriteConvention.cs:14-16
    /// states: anything left on Default draws behind everything on WorldSprites whatever number it
    /// carries. So the durable property is that WorldSprites exists and sorts AFTER Default.
    /// </para>
    /// <para>
    /// Reads Editor API state only. It opens no scene and writes nothing, so it cannot dirty a
    /// tracked asset.
    /// </para>
    /// </remarks>
    public class WorldSpriteSortingLayerDeclarationTests
    {
        private const string DefaultLayerName = "Default";

        [Test]
        public void WorldSpriteSortingLayer_IsDeclaredInProjectSettings()
        {
            string[] declared = SortingLayer.layers.Select(layer => layer.name).ToArray();

            // The control: Unity guarantees Default, so an empty or broken read fails here first
            // rather than reporting the layer under test as missing.
            Assert.Contains(DefaultLayerName, declared,
                "SortingLayer.layers does not even contain '" + DefaultLayerName + "', which Unity "
                + "always declares. Suspect this read before concluding anything about the layer "
                + "under test. Saw: " + string.Join(", ", declared));

            Assert.Contains(WorldSpriteConvention.SortingLayerName, declared,
                "ProjectSettings/TagManager.asset no longer declares the sorting layer '"
                + WorldSpriteConvention.SortingLayerName + "' that WorldSpriteConvention names and "
                + "every world sprite draws on. Every renderer assigned to it would fall back to "
                + DefaultLayerName + " and draw in the wrong order, with no compile error. Saw: "
                + string.Join(", ", declared));
        }

        [Test]
        public void WorldSpriteSortingLayer_SortsAfterDefault()
        {
            int worldSprites = SortingLayer.GetLayerValueFromName(WorldSpriteConvention.SortingLayerName);
            int fallback = SortingLayer.GetLayerValueFromName(DefaultLayerName);

            Assert.Greater(worldSprites, fallback,
                "The sorting layer '" + WorldSpriteConvention.SortingLayerName + "' has layer value "
                + worldSprites + " against " + DefaultLayerName + "'s " + fallback + ", so world "
                + "sprites would draw BEHIND anything left on " + DefaultLayerName + ". The layer's "
                + "position in ProjectSettings/TagManager.asset decides this, not any sortingOrder "
                + "a renderer sets, so no per-object number can compensate for it.");
        }
    }
}
