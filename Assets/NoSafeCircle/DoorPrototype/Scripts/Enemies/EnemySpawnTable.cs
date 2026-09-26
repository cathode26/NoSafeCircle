using System;
using System.Collections.Generic;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Enemies
{
    /// <summary>Which prefab a spawn entry stands for. The values are serialized; append, never reorder.</summary>
    public enum EnemyKind
    {
        Melee = 0,
        LanternWraith = 1
    }

    /// <summary>One authored spawn point. Read-only at runtime (ENGINEERING_STANDARDS 11).</summary>
    [Serializable]
    public sealed class EnemySpawnEntry
    {
        [SerializeField] private string id;
        [SerializeField] private EnemyKind kind;
        [SerializeField] private string room;
        [SerializeField] private Vector3 position;

        // Unity's serializer needs the parameterless constructor; the other one is for fixtures.
        public EnemySpawnEntry()
        {
        }

        public EnemySpawnEntry(string id, EnemyKind kind, string room, Vector3 position)
        {
            this.id = id;
            this.kind = kind;
            this.room = room;
            this.position = position;
        }

        /// <summary>Unique within its table; the pool slot name, e.g. "lv-melee-1".</summary>
        public string Id => id;

        public EnemyKind Kind => kind;

        /// <summary>The room the point lies in, for a human and for the bounds test. Nothing at
        /// runtime derives anything from it.</summary>
        public string Room => room;

        /// <summary>World position, y = 0. Pinned by acceptance criteria (AC-005 door-line
        /// relations, AC-006 navmesh sampling), never derived from a map, never snapped to a grid.</summary>
        public Vector3 Position => position;
    }

    /// <summary>
    /// The nine authored enemy spawn points, as data the Enemies lane owns.
    /// </summary>
    /// <remarks>
    /// <para>
    /// WHY THIS IS AN ASSET AND NOT A LITERAL. The points lived in
    /// <c>Editor/World/DoorPrototypeGlobalSceneBuilder.cs</c> as two private arrays, which runtime
    /// code cannot reference (ENGINEERING_STANDARDS 13: runtime never references Editor
    /// assemblies). Standards 11 says enemy definitions and encounters are ScriptableObjects,
    /// immutable at runtime. So the arrays moved here VERBATIM - <c>Tests/Editor/EnemySpawnTableTests</c>
    /// compares the asset against the editor arrays by reflection and against a second literal
    /// copy, so a transcription error cannot pass.
    /// </para>
    /// <para>
    /// NONE OF THE POINTS IS ON ANY LATTICE, AND THAT IS NOT UNTIDINESS. (-4.5, 0, 64.75) sits
    /// where it does because AC-006 needs NavMesh.SamplePosition to succeed within 0.1 of the
    /// authored y=0 and the previous point measured 0.129. Do not round them, regenerate them, or
    /// snap them to a grid; the acceptance criteria pin them.
    /// </para>
    /// </remarks>
    [CreateAssetMenu(menuName = "No Safe Circle/Enemy Spawn Table", fileName = "EnemySpawnTable")]
    public sealed class EnemySpawnTable : ScriptableObject
    {
        [SerializeField] private EnemySpawnEntry[] entries = new EnemySpawnEntry[0];

        public IReadOnlyList<EnemySpawnEntry> Entries => entries;

        /// <summary>A table that lives only in memory, for fixtures. Production reads the asset.</summary>
        public static EnemySpawnTable CreateRuntime(IEnumerable<EnemySpawnEntry> source)
        {
            var table = CreateInstance<EnemySpawnTable>();
            table.entries = new List<EnemySpawnEntry>(source).ToArray();
            return table;
        }

        /// <summary>Standards 11: report missing ids, duplicate ids and invalid values before
        /// play. The spawner refuses a table that fails this rather than spawning part of it.</summary>
        public bool TryValidate(out string problem)
        {
            if (entries == null || entries.Length == 0)
            {
                problem = "the table has no entries";
                return false;
            }

            var seen = new HashSet<string>();
            for (int i = 0; i < entries.Length; i++)
            {
                EnemySpawnEntry entry = entries[i];
                if (entry == null)
                {
                    problem = $"entry {i} is null";
                    return false;
                }

                if (string.IsNullOrWhiteSpace(entry.Id))
                {
                    problem = $"entry {i} has no id";
                    return false;
                }

                if (!seen.Add(entry.Id))
                {
                    problem = $"id '{entry.Id}' is repeated";
                    return false;
                }

                if (!Enum.IsDefined(typeof(EnemyKind), entry.Kind))
                {
                    problem = $"'{entry.Id}' has an unknown kind {(int)entry.Kind}";
                    return false;
                }

                Vector3 p = entry.Position;
                if (float.IsNaN(p.x) || float.IsNaN(p.y) || float.IsNaN(p.z)
                    || float.IsInfinity(p.x) || float.IsInfinity(p.y) || float.IsInfinity(p.z))
                {
                    problem = $"'{entry.Id}' has a non-finite position";
                    return false;
                }
            }

            problem = null;
            return true;
        }
    }
}
