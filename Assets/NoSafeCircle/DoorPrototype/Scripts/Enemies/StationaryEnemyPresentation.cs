using System;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    [DisallowMultipleComponent]
    [RequireComponent(typeof(SpriteRenderer))]
    public sealed class StationaryEnemyPresentation : MonoBehaviour
    {
        private const int DirectionCount = 8;

        [SerializeField] private StationaryEnemyArchetype archetype;
        [SerializeField] private StationaryEnemyDirection facing;
        [SerializeField] private Sprite[] facingSprites = new Sprite[DirectionCount];

        public StationaryEnemyArchetype Archetype => archetype;
        public StationaryEnemyDirection Facing => facing;

        public Sprite SpriteFor(StationaryEnemyDirection direction)
        {
            int index = (int)direction;
            if (index < 0 || index >= DirectionCount || facingSprites == null ||
                facingSprites.Length != DirectionCount)
            {
                throw new ArgumentOutOfRangeException(nameof(direction));
            }

            return facingSprites[index];
        }

        public void Configure(StationaryEnemyArchetype enemyArchetype,
            StationaryEnemyDirection initialFacing, Sprite[] sprites)
        {
            if (sprites == null || sprites.Length != DirectionCount)
            {
                throw new ArgumentException("Exactly eight direction-explicit Sprites are required.", nameof(sprites));
            }

            foreach (Sprite sprite in sprites)
            {
                if (sprite == null)
                {
                    throw new ArgumentException("A direction Sprite is missing.", nameof(sprites));
                }
            }

            archetype = enemyArchetype;
            facingSprites = (Sprite[])sprites.Clone();
            SetFacing(initialFacing);
        }

        public void SetFacing(StationaryEnemyDirection direction)
        {
            Sprite sprite = SpriteFor(direction);
            facing = direction;
            GetComponent<SpriteRenderer>().sprite = sprite;
        }

        private void OnEnable()
        {
            int index = (int)facing;
            if (index >= 0 && index < DirectionCount && facingSprites != null &&
                facingSprites.Length == DirectionCount && facingSprites[index] != null)
            {
                GetComponent<SpriteRenderer>().sprite = facingSprites[index];
            }
        }
    }
}
