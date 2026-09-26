using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.World
{
    // The runtime-readable shape of a *DressingCatalog.json. These are the Art Director's authored
    // placements - 222 of them across five rooms - and this file is the first time they can be read
    // at PLAY rather than only at edit time.
    //
    // WHY THIS EXISTS. Vincent, 2026-09-26: "No we must stop this baking thing", "I write code to
    // instantiate prefabs", "The scene should just be some objects that create prefabs". The
    // catalogs were already the right thing; they were simply consumed by an editor builder that
    // baked its output into a committed prefab. Nothing about the DATA changes here. Only when it
    // is read.
    //
    // FIELD NAMES ARE NOT A CHOICE. JsonUtility binds by exact field name, and these names are
    // copied from the editor DTOs in *DressingPrefabBuilder.cs so the SAME json binds in both
    // places during the migration. Renaming one to something more C#-idiomatic silently yields a
    // default value rather than an error - which is the failure mode this comment exists to stop.
    [Serializable]
    public sealed class RoomDressingCatalog
    {
        public string room;
        public DressingPlacement[] props;
    }

    [Serializable]
    public sealed class DressingPlacement
    {
        public string instance_id;
        public string prop_id;
        public string footprint;
        public CatalogPosition position;
        public float rotation_euler_z;

        // KEPT AND DELIBERATELY NOT APPLIED TO A RENDERER. The authored sorting_order stays in the
        // catalogs and is still checked against the rule the catalog declares, but every world
        // sprite sits at one shared sortingOrder so the camera's transparency axis decides depth by
        // POSITION. An integer order is compared BEFORE that axis and wins unconditionally, which
        // is how a bookshelf came to render in front of a wizard standing behind it.
        public int sorting_order;
    }

    [Serializable]
    public sealed class CatalogPosition
    {
        public float x;
        public float y;
        public float z;
    }
}
