using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
using NoSafeCircle.DoorPrototype.World;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    // NSC-089 AC-002/VAL-001: proves GameplayNavigationSurface bakes with the project's single
    // configured NavMesh agent type and that a test-owned NavMeshAgent using that same type finds
    // a complete path on an isolated in-memory floor. The underlying NavMeshSurface type lives in
    // the Unity.AI.Navigation package assembly, which only the runtime NoSafeCircle.DoorPrototype
    // asmdef is authorized to reference (AC-002); this test assembly reads NavMeshSurface's public
    // properties through reflection instead of adding that reference here.
    //
    // The committed-scene conformance check that used to live here (against
    // Assets/Scenes/DoorPrototype.unity) was removed when that scene was deleted. Its coverage is
    // NOT replaced: nothing here proves the composed RuntimeWorld rooms are walkable end to end --
    // NavigationSpawnerPlayModeTests' own comment already admits it does not prove that either.
    public sealed class NavMeshAgentConfigurationTests
    {
        private const string GameplayNavigationRootName = "GameplayNavigation";

        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        // AC-002/VAL-001: in-memory scene proof. GameplayNavigationSurface must configure its
        // NavMeshSurface with the project's single configured agent type, collecting gameplay
        // collision colliders (never visual Tilemap renderers), and a test-owned NavMeshAgent
        // using that same agent type must find a complete path across a test-owned open floor.
        [Test]
        public void ConfigureAndBuild_OnOpenTestFloor_MatchesProjectAgentTypeAndAgentFindsCompletePath()
        {
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.name = "TestGameplayFloor";
            floor.transform.position = Vector3.zero;
            floor.transform.localScale = new Vector3(20f, 0.1f, 20f);

            var navigationRoot = new GameObject(GameplayNavigationRootName);
            var surfaceOwner = navigationRoot.AddComponent<GameplayNavigationSurface>();
            surfaceOwner.ConfigureAndBuild();

            var expectedSettings = NavMesh.GetSettingsByIndex(0);
            var surface = GetSurface(surfaceOwner);
            Assert.AreEqual(expectedSettings.agentTypeID, (int)GetPublicProperty(surface, "agentTypeID"),
                "GameplayNavigationSurface must bake with the project's single configured agent type.");
            Assert.AreEqual("All", GetPublicProperty(surface, "collectObjects").ToString(),
                "GameplayNavigationSurface must collect gameplay collision from the whole scene.");
            Assert.AreEqual("PhysicsColliders", GetPublicProperty(surface, "useGeometry").ToString(),
                "GameplayNavigationSurface must bake from physics colliders (gameplay truth), never Tilemap renderers.");

            Assert.IsTrue(NavMesh.SamplePosition(new Vector3(-9f, 0f, -9f), out var startHit, 2f, NavMesh.AllAreas),
                "Expected a walkable NavMesh point near one side of the open test floor.");
            Assert.IsTrue(NavMesh.SamplePosition(new Vector3(9f, 0f, 9f), out var endHit, 2f, NavMesh.AllAreas),
                "Expected a walkable NavMesh point near the opposite side of the open test floor.");

            var agentObject = new GameObject("TestNavMeshAgent");
            agentObject.transform.position = startHit.position;
            var agent = agentObject.AddComponent<NavMeshAgent>();
            agent.agentTypeID = expectedSettings.agentTypeID;
            agent.radius = expectedSettings.agentRadius;
            agent.height = expectedSettings.agentHeight;
            agent.Warp(startHit.position);

            Assert.AreEqual(expectedSettings.agentTypeID, agent.agentTypeID,
                "The test-owned NavMeshAgent must use the same project agent type as the baked surface.");

            // Edit Mode does not run the NavMeshAgent activation/update loop. CalculatePath on an
            // unactivated component therefore reports that the agent is not placed on a NavMesh,
            // even though the baked NavMesh is valid. Static CalculatePath exercises the same
            // baked polygons here; the agent type binding is asserted above and true agent
            // activation remains a Play Mode concern.
            var path = new NavMeshPath();
            var foundPath = NavMesh.CalculatePath(startHit.position, endHit.position, NavMesh.AllAreas, path);

            Assert.IsTrue(foundPath,
                "Expected the test-owned NavMeshAgent to compute a path across the open test floor.");
            Assert.AreEqual(NavMeshPathStatus.PathComplete, path.status,
                "The test-owned NavMeshAgent must find a complete path across the open gameplay floor baked by GameplayNavigationSurface.");
        }

        private static object GetSurface(GameplayNavigationSurface surfaceOwner)
        {
            var surfaceProperty = typeof(GameplayNavigationSurface).GetProperty("Surface");
            Assert.IsNotNull(surfaceProperty, "Expected a public 'Surface' property on GameplayNavigationSurface.");

            var surface = surfaceProperty.GetValue(surfaceOwner);
            Assert.IsNotNull(surface, "Expected GameplayNavigationSurface.Surface to resolve the underlying NavMeshSurface.");
            return surface;
        }

        private static object GetPublicProperty(object instance, string propertyName)
        {
            var property = instance.GetType().GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);
            Assert.IsNotNull(property, $"Expected a public property '{propertyName}' on '{instance.GetType().Name}'.");
            return property.GetValue(instance);
        }
    }
}
