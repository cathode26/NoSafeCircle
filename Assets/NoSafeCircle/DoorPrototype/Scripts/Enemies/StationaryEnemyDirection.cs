namespace NoSafeCircle.DoorPrototype.Enemies
{
    public enum StationaryEnemyArchetype
    {
        Melee,
        Ranged
    }

    // The enum order is also the stable Sprite array order in the generated prefabs.
    public enum StationaryEnemyDirection
    {
        North,
        NorthEast,
        East,
        SouthEast,
        South,
        SouthWest,
        West,
        NorthWest
    }
}
