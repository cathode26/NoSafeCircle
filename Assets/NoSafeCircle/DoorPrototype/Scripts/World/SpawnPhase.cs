namespace NoSafeCircle.DoorPrototype.World
{
    /// <summary>
    /// The order in which the world builds itself at Play. One value per family.
    /// </summary>
    /// <remarks>
    /// <para>
    /// THE ORDER IS THE CONTRACT BETWEEN SEVEN INDEPENDENT LANES. Vincent, 2026-09-26: "I never want
    /// to work in these big scenes. Lets create everything with instantiate from now on." Each family
    /// is authored by a different agent in a different worktree, and the only thing they must agree
    /// on is WHEN they run. Putting that agreement in one enum means a lane can be written, tested
    /// and merged without reading any other lane's code.
    /// </para>
    /// <para>
    /// THE NUMBERS ARE EXPLICIT BECAUSE THEY ARE SORTED ON. Reordering the members would silently
    /// change the build order of the whole game, so each phase states its own position and a reader
    /// can see the sequence without counting.
    /// </para>
    /// <para>
    /// WHY THESE DEPENDENCIES, shortest form: navigation must bake AFTER the props exist or it walks
    /// through them - which is the same fact the prop colliders were added for, seen from the
    /// navmesh's side. Doors need their room's wall run to exist so they can sit in its opening. The
    /// player and the enemies need somewhere to stand, which means navigation. The HUD is last
    /// because it binds to a player that must already exist.
    /// </para>
    /// </remarks>
    public enum SpawnPhase
    {
        /// <summary>Floors and walls. Nothing else has anywhere to be until this runs.</summary>
        Rooms = 0,

        /// <summary>The Art Director's authored dressing. Solid props, so navigation must follow.</summary>
        Props = 1,

        /// <summary>The navmesh, built around everything solid that now exists.</summary>
        Navigation = 2,

        /// <summary>Door instances in the openings their rooms left for them.</summary>
        Doors = 3,

        /// <summary>The wizard, at a spawn point navigation can sample.</summary>
        Player = 4,

        /// <summary>Enemies and their pools, which need the player to exist to have a target.</summary>
        Enemies = 5,

        /// <summary>UI, last, because it binds to the player.</summary>
        Hud = 6
    }
}
