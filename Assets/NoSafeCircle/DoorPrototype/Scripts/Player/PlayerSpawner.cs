using NoSafeCircle.DoorPrototype.Navigation;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Player
{
    // Instantiates the wizard and the isometric camera AT RUNTIME, from two authored prefabs, at
    // the Ruined Entry start the room layout already declares.
    //
    // WHAT IT REPLACES. DoorPrototypeGlobalSceneBuilder.BuildPlayer (Editor assembly) created the
    // player with `new GameObject` and nine AddComponent calls, set twelve private fields by
    // reflection, computed the visual scale from a sprite it loaded through AssetDatabase, and
    // BAKED the result into a committed scene; BuildCamera did the same for the camera. Neither
    // runs in the built game, and the scene they wrote is the one artifact nobody can merge.
    // Here the PREFABS are the authored artifact: Resources/Player/Player.prefab carries every
    // component, reference and literal (sprite, sorting, scale, input asset, animator controller),
    // and this component sets POSITION and nothing else - the PropSpawner shape, one lane up.
    //
    // THE WIZARD MOVES BY LEFT-CLICKING THE FLOOR. PlayerMovement reads PointerPosition and
    // MoveToCursor from the input asset the prefab references and projects the cursor through
    // Camera.main onto the y = 0 plane - a mathematical Plane, not a physics raycast, so clicking
    // needs no floor collider. WASD is bound in that asset and read by nothing; nothing here
    // designs around it.
    [DisallowMultipleComponent]
    public sealed class PlayerSpawner : MonoBehaviour, ISpawner
    {
        /// The hierarchy name other fixtures look up with GameObject.Find("Player") - the editor
        /// builder tests, TitleScreen and WizardGameEntry. Kept so nothing downstream moves.
        public const string PlayerObjectName = "Player";

        /// The camera's name, kept equal to the builder's so a scene reader sees the same thing.
        public const string CameraObjectName = "Main Camera";

        /// The tag Camera.main resolves. The runtime scene's placeholder carries it too, which is
        /// why Spawn() retires that placeholder before creating the real camera.
        private const string MainCameraTag = "MainCamera";

        [Tooltip("Resources/Player/Player.prefab: the wizard with every component, reference and "
            + "literal it needs. This spawner adds nothing to it but a position.")]
        [SerializeField] private GameObject playerPrefab;

        [Tooltip("Resources/Player/IsometricCamera.prefab: orthographic, size 8, Euler (30,-45,0), "
            + "carrying the IsometricCameraFollow that re-applies the sprite sorting axis.")]
        [SerializeField] private GameObject cameraPrefab;

        [Tooltip("World-space offset from the wizard to the camera. A fixed, hand-picked framing, "
            + "deliberately NOT derived from the camera's rotation; carried from the editor "
            + "builder's IsometricCameraOffset (10, 10, -10).")]
        [SerializeField] private Vector3 cameraOffset = new Vector3(10f, 10f, -10f);

        /// After Navigation, so the start can be sampled and enemies can path to the wizard; before
        /// Enemies and Hud, which both find the wizard by type.
        public SpawnPhase Phase => SpawnPhase.Player;

        /// The wizard created by the last Spawn(), or null before one has run.
        public PlayerMovement Player { get; private set; }

        /// The camera created by the last Spawn(), or null before one has run.
        public Camera Camera { get; private set; }

        /// Objects created by the last Spawn(): the wizard and the camera. -1 until Spawn() has
        /// run, which is deliberately distinguishable from a Spawn() that refused and created nothing.
        public int SpawnedCount { get; private set; } = -1;

        /// Creates the wizard and the camera. Safe to call again: it clears what it previously
        /// created first, so a rebuild cannot leave two wizards or two main cameras.
        public int Spawn()
        {
            ClearPreviousSpawn();

            if (IsMissing(playerPrefab, nameof(playerPrefab))
                || IsMissing(cameraPrefab, nameof(cameraPrefab))
                || IsMissing<CharacterController>(playerPrefab, nameof(playerPrefab))
                || IsMissing<PlayerMovement>(playerPrefab, nameof(playerPrefab))
                || IsMissing<Camera>(cameraPrefab, nameof(cameraPrefab))
                || IsMissing<IsometricCameraFollow>(cameraPrefab, nameof(cameraPrefab)))
            {
                SpawnedCount = 0;
                return 0;
            }

            // THE START IS THE LAYOUT'S, read at runtime; the editor builder read the same constant.
            // The y is the CharacterController's skinWidth: the controller settles one skinWidth
            // above whatever it stands on, so spawning there means Play does not open with the
            // wizard visibly dropping onto the floor.
            Vector3 start = RuinedEntryLayout.PlayerStart;
            float skin = playerPrefab.GetComponent<CharacterController>().skinWidth;
            var pose = new Vector3(start.x, skin, start.z);

            // THE POSITION OVERLOAD, NOT INSTANTIATE-THEN-MOVE. PlayerMovement.Awake records
            // initialPosition and ResetMovement (the death restart) warps back to it. Awake runs
            // inside Instantiate, so an object moved afterwards would restart at the origin.
            GameObject player = Instantiate(playerPrefab, pose, Quaternion.identity, transform);
            player.name = PlayerObjectName;
            Player = player.GetComponent<PlayerMovement>();

            ExcludeFromNavMeshRebuilds(player);
            RetirePlaceholderCameras();

            // The prefab owns the rotation (Euler 30, -45, 0) and this spawner owns only the offset,
            // so there is one copy of each. Initialize captures offset = camera - target from the
            // CURRENT transforms, so the framing is exactly that rotation plus cameraOffset.
            GameObject cameraObject = Instantiate(cameraPrefab, pose + cameraOffset,
                cameraPrefab.transform.rotation, transform);
            cameraObject.name = CameraObjectName;
            cameraObject.GetComponent<IsometricCameraFollow>().Initialize(player.transform);
            Camera = cameraObject.GetComponent<Camera>();

            SpawnedCount = 2;
            Debug.Log($"{nameof(PlayerSpawner)}: spawned '{player.name}' at {pose} and "
                + $"'{cameraObject.name}' at {cameraObject.transform.position}.");
            return SpawnedCount;
        }

        // DEACTIVATE, THEN DESTROY. Destroy is deferred to the end of the frame, and the Enemies and
        // Hud spawners find the wizard with FindFirstObjectByType, which skips inactive objects; so
        // does Camera.main. Deactivating first means a same-frame rebuild can never bind a later
        // phase to the dying wizard or the dying camera.
        private void ClearPreviousSpawn()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                GameObject child = transform.GetChild(i).gameObject;
                child.SetActive(false);
                Destroy(child);
            }

            Player = null;
            Camera = null;
        }

        // ANYTHING SPAWNED AFTER NAVIGATION GETS NavMeshModifier { ignoreFromBuild, applyToChildren }
        // ON ITS ROOT. The first bake is correct by phase order (Navigation is 2, Player is 4), but a
        // rebuild - BuildWorld twice, or a scene reload in one session - re-bakes with the previous
        // wizard still alive for one frame, and his CharacterController is a physics collider the
        // bake collects. NavigationSpawner audits for exactly this before every bake and LogErrors
        // each violator by hierarchy path, so a miss here fails GameBootstrapPlayModeTests.
        //
        // APPLIED AT SPAWN THROUGH THE NAVIGATION LANE'S SEAM RATHER THAN AUTHORED INTO
        // Player.prefab, for one measured reason: Tools/prefab_lint.py resolves every m_Script guid
        // against Assets/**/*.meta only, and NavMeshModifier lives in the com.unity.ai.navigation
        // PACKAGE (guid 1e3fdca004f2d45fe8abbed571a8abd5, indexed nowhere under Assets), so a
        // prefab carrying it fails the lint every lane must pass. Applying it at spawn is equivalent
        // for every rebuild, because a rebuild can only start after this Spawn() has returned, and
        // the seam states the rule once instead of this lane restating it.
        private static void ExcludeFromNavMeshRebuilds(GameObject player)
        {
            NavMeshRebakeExclusion.Apply(player);
        }

        // THE RUNTIME SCENE STILL HOLDS A PLACEHOLDER "Main Camera". SceneStubTests.AllowedRoots says
        // it belongs to this lane and is expected to leave when the lane ships, but the scene is the
        // one file no lane may edit, so the bridge is a runtime state change: disable the
        // placeholder's Camera and AudioListener so Camera.main resolves the real camera and Unity
        // does not warn about two listeners. The warning is the reminder for the scene's owner to
        // delete the root and the AllowedRoots entry in one commit.
        private void RetirePlaceholderCameras()
        {
            foreach (Camera existing in FindObjectsByType<Camera>(FindObjectsSortMode.None))
            {
                if (!existing.CompareTag(MainCameraTag))
                {
                    continue;
                }

                existing.enabled = false;
                var listener = existing.GetComponent<AudioListener>();
                if (listener != null)
                {
                    listener.enabled = false;
                }

                Debug.LogWarning($"{nameof(PlayerSpawner)}: disabled placeholder camera "
                    + $"'{existing.name}'. The scene owner should remove it; see "
                    + "SceneStubTests.AllowedRoots.");
            }
        }

        private static bool IsMissing(GameObject prefab, string field)
        {
            if (prefab != null)
            {
                return false;
            }

            Debug.LogError($"{nameof(PlayerSpawner)}: '{field}' is not assigned, so neither the "
                + "wizard nor the camera can be created. Assign it on Resources/Spawners/PlayerSpawner.");
            return true;
        }

        private static bool IsMissing<T>(GameObject prefab, string field) where T : Component
        {
            if (prefab.GetComponent<T>() != null)
            {
                return false;
            }

            Debug.LogError($"{nameof(PlayerSpawner)}: '{field}' ({prefab.name}) has no "
                + $"{typeof(T).Name}, which the spawn depends on.");
            return true;
        }
    }
}
