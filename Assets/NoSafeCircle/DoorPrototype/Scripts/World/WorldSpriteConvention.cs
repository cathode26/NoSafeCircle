namespace NoSafeCircle.DoorPrototype.World
{
    // THE one definition of how anything in the world sorts. Runtime assembly, deliberately.
    //
    // WHY IT MOVED HERE. These four values lived on DoorPrototypeSceneBuilder, in the EDITOR
    // assembly, because everything that needed them was an editor builder. Under Vincent's
    // direction the world is now assembled at Play - "The scene should just be some objects that
    // create prefabs" - so runtime code needs them, and runtime code cannot reference an Editor
    // assembly. The editor constants now forward here, so there is still exactly ONE definition
    // and every existing test that names them keeps compiling.
    //
    // THE HISTORY THAT MAKES THESE LOAD-BEARING, so nobody "tidies" them:
    //
    // SortingLayerName - the sorting LAYER is compared BEFORE sortingOrder, and it is the layer's
    //   INDEX that decides. "Default" is index 0 and "WorldSprites" is index 1, so anything left on
    //   Default draws behind everything on WorldSprites whatever number it carries. Five baked
    //   prefabs sat on Default for a night and Vincent photographed the result: 222 props
    //   instantiated and not drawn. A test that asserted the literal "Default" kept passing the
    //   whole time.
    //
    // SortingOrder - ONE shared order for every world sprite, so depth comes from the camera's
    //   transparencySortAxis by POSITION. An integer order is compared BEFORE that axis and wins
    //   unconditionally: all 22 Bone Archive shelves were authored -219..-36 against a wizard at 0,
    //   so no shelf could occlude him at ANY position. Walls are Tilemaps and a TilemapRenderer has
    //   ONE order for an entire run - Unity has no per-tile order - so walls cannot carry
    //   per-position depth and must stay on the axis; the wizard must stay there to sort against
    //   walls; therefore the props had to come there too. The constraint runs walls -> wizard ->
    //   props and there is no arrangement that keeps authored integers AND lets walls occlude.
    //
    // The two background orders - floors and the architectural border sit below every world sprite.
    //   short.MinValue rather than a small negative because Renderer.sortingOrder is a signed 16-bit
    //   field in Unity's sorting key: out of range wraps silently to a large POSITIVE, which would
    //   put the floor in front of everything. The +10 gap is deliberate adjacency: the border must
    //   be above the ground and still below every sprite, and a gap of 10 leaves room to insert a
    //   background layer later without renumbering. Both were -100/-90 until a catalog prop was
    //   authored at -1165 and went under the floor.
    public static class WorldSpriteConvention
    {
        /// The sorting layer every world sprite and every world tilemap belongs to.
        public const string SortingLayerName = "WorldSprites";

        /// The single shared order for every world sprite, so the camera's transparency axis
        /// decides depth by position rather than an authored integer overruling it.
        public const int SortingOrder = 0;

        /// Room floors. Below every world sprite, and at the bottom of what Unity can represent.
        public const int BackgroundGroundSortingOrder = short.MinValue;

        /// The architectural border: above the ground, below every world sprite.
        public const int BackgroundArchitecturalBorderSortingOrder = short.MinValue + 10;
    }
}
