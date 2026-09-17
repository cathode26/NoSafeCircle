using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

namespace NoSafeCircle.DoorPrototype
{
    /// Playable-build run flow: enemy contact damage, a cursor-aimed fireball that costs mana,
    /// enemy health bars, and the win/loss end states the run needs. Deliberately self-contained
    /// and IMGUI-driven so a build has a visible ending without depending on unbuilt UI tasks.
    public sealed class DemoRunFlow : MonoBehaviour
    {
        [SerializeField] private PlayerHealth playerHealth;
        [SerializeField] private PlayerMana playerMana;
        [SerializeField] private Transform player;

        [SerializeField] private float enemyContactRange = 1.6f;
        [SerializeField] private float enemyDamagePerHit = 12f;
        [SerializeField] private float enemyAttackInterval = 1.0f;

        [SerializeField] private float fireballSpeed = 12f;
        [SerializeField] private float fireballLifetime = 3f;
        [SerializeField] private float fireballHitRadius = 0.9f;
        [SerializeField] private float fireballDamage = 25f;
        [SerializeField] private float fireballManaCost = 20f;
        [SerializeField] private float fireballCooldown = 0.5f;

        [SerializeField] private float healthBarWidth = 46f;
        [SerializeField] private float healthBarHeight = 6f;
        [SerializeField] private float healthBarHeightAboveEnemy = 2.2f;

        private readonly List<Fireball> fireballs = new List<Fireball>();
        private float attackCooldown;
        private float castCooldown;
        private bool won;
        private bool lost;

        private struct Fireball
        {
            public GameObject Visual;
            public Vector3 Direction;
            public float RemainingLifetime;
        }

        private void Start()
        {
            if (player == null)
            {
                var movement = FindFirstObjectByType<PlayerMovement>();
                if (movement != null) player = movement.transform;
            }

            if (player != null)
            {
                if (playerHealth == null) playerHealth = player.GetComponent<PlayerHealth>();
                if (playerMana == null) playerMana = player.GetComponent<PlayerMana>();
            }

            if (playerHealth != null) playerHealth.Died += HandlePlayerDied;

            foreach (DoorInteractable door in FindObjectsByType<DoorInteractable>(FindObjectsSortMode.None))
            {
                if (door.IsFinalDoor) door.CrossedForward += HandleFinalDoorCrossed;
            }
        }

        private void OnDestroy()
        {
            if (playerHealth != null) playerHealth.Died -= HandlePlayerDied;
        }

        private void HandlePlayerDied()
        {
            lost = true;
        }

        private void HandleFinalDoorCrossed()
        {
            won = true;
        }

        private void Update()
        {
            if (won || lost) return;

            if (castCooldown > 0f) castCooldown -= Time.deltaTime;

            AdvanceFireballs(Time.deltaTime);
            TryFireAtCursor();
            ApplyEnemyContactDamage(Time.deltaTime);
        }

        private void TryFireAtCursor()
        {
            Mouse mouse = Mouse.current;
            if (mouse == null || player == null || !mouse.rightButton.wasPressedThisFrame) return;
            if (castCooldown > 0f) return;

            // Mana gates casting exactly as it does for the enemy caster, so a wizard that
            // regenerates faster genuinely sustains more fire.
            if (playerMana != null && !playerMana.Spend(fireballManaCost)) return;

            Camera camera = Camera.main;
            if (camera == null) return;

            // Aim across the gameplay plane at the wizard's own height.
            var plane = new Plane(Vector3.up, new Vector3(0f, player.position.y, 0f));
            Ray ray = camera.ScreenPointToRay(mouse.position.ReadValue());
            if (!plane.Raycast(ray, out float distance)) return;

            Vector3 target = ray.GetPoint(distance);
            Vector3 direction = target - player.position;
            direction.y = 0f;
            if (direction.sqrMagnitude < 0.0001f) return;

            var visual = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            visual.name = "Fireball";
            Destroy(visual.GetComponent<Collider>());
            visual.transform.localScale = Vector3.one * 0.5f;
            visual.transform.position = player.position + Vector3.up + direction.normalized;

            Renderer renderer = visual.GetComponent<Renderer>();
            if (renderer != null) renderer.material.color = new Color(1f, 0.45f, 0.1f);

            fireballs.Add(new Fireball
            {
                Visual = visual,
                Direction = direction.normalized,
                RemainingLifetime = fireballLifetime,
            });

            castCooldown = fireballCooldown;
        }

        private void AdvanceFireballs(float deltaTime)
        {
            for (int index = fireballs.Count - 1; index >= 0; index--)
            {
                Fireball fireball = fireballs[index];
                if (fireball.Visual == null)
                {
                    fireballs.RemoveAt(index);
                    continue;
                }

                fireball.Visual.transform.position += fireball.Direction * (fireballSpeed * deltaTime);
                fireball.RemainingLifetime -= deltaTime;

                bool consumed = false;
                foreach (EnemyHealth enemy in FindObjectsByType<EnemyHealth>(FindObjectsSortMode.None))
                {
                    if (enemy.IsDefeated) continue;

                    float hitDistance = Vector3.Distance(
                        new Vector3(enemy.transform.position.x, 0f, enemy.transform.position.z),
                        new Vector3(fireball.Visual.transform.position.x, 0f, fireball.Visual.transform.position.z));
                    if (hitDistance > fireballHitRadius) continue;

                    enemy.TakeDamage(fireballDamage);

                    // EnemyHealth reports defeat but never removes the GameObject, so a defeated
                    // enemy would keep pursuing and keep dealing contact damage without this.
                    if (enemy.IsDefeated) Destroy(enemy.gameObject);

                    consumed = true;
                    break;
                }

                if (consumed || fireball.RemainingLifetime <= 0f)
                {
                    Destroy(fireball.Visual);
                    fireballs.RemoveAt(index);
                    continue;
                }

                fireballs[index] = fireball;
            }
        }

        private void ApplyEnemyContactDamage(float deltaTime)
        {
            if (player == null || playerHealth == null) return;

            attackCooldown -= deltaTime;
            if (attackCooldown > 0f) return;

            foreach (EnemyHealth enemy in FindObjectsByType<EnemyHealth>(FindObjectsSortMode.None))
            {
                if (enemy.IsDefeated) continue;

                float contactDistance = Vector3.Distance(
                    new Vector3(enemy.transform.position.x, 0f, enemy.transform.position.z),
                    new Vector3(player.position.x, 0f, player.position.z));
                if (contactDistance > enemyContactRange) continue;

                playerHealth.TakeDamage(enemyDamagePerHit);
                attackCooldown = enemyAttackInterval;
                return;
            }
        }

        private void OnGUI()
        {
            if (!won && !lost)
            {
                DrawEnemyHealthBars();
                DrawPlayerStatus();
                return;
            }

            DrawEndScreen();
        }

        /// A small bar above any enemy that has taken damage, so the wizard can tell a wounded
        /// enemy from a fresh one. Undamaged enemies stay unmarked to keep the screen quiet.
        private void DrawEnemyHealthBars()
        {
            Camera camera = Camera.main;
            if (camera == null) return;

            foreach (EnemyHealth enemy in FindObjectsByType<EnemyHealth>(FindObjectsSortMode.None))
            {
                if (enemy.IsDefeated) continue;
                if (enemy.MaxHealth <= 0f) continue;
                if (enemy.CurrentHealth >= enemy.MaxHealth) continue;

                Vector3 worldAnchor = enemy.transform.position + Vector3.up * healthBarHeightAboveEnemy;
                Vector3 screenPoint = camera.WorldToScreenPoint(worldAnchor);
                if (screenPoint.z <= 0f) continue;

                float left = screenPoint.x - healthBarWidth * 0.5f;
                float top = Screen.height - screenPoint.y;
                float fraction = Mathf.Clamp01(enemy.CurrentHealth / enemy.MaxHealth);

                GUI.color = new Color(0f, 0f, 0f, 0.65f);
                GUI.DrawTexture(
                    new Rect(left - 1f, top - 1f, healthBarWidth + 2f, healthBarHeight + 2f),
                    Texture2D.whiteTexture);

                GUI.color = Color.Lerp(new Color(0.85f, 0.15f, 0.15f), new Color(0.3f, 0.85f, 0.3f), fraction);
                GUI.DrawTexture(
                    new Rect(left, top, healthBarWidth * fraction, healthBarHeight),
                    Texture2D.whiteTexture);

                GUI.color = Color.white;
            }
        }

        private void DrawPlayerStatus()
        {
            if (playerHealth == null) return;

            var style = new GUIStyle(GUI.skin.label) { fontSize = 20, fontStyle = FontStyle.Bold };
            style.normal.textColor = Color.white;

            GUI.Label(new Rect(20f, 16f, 400f, 32f),
                $"Health {Mathf.CeilToInt(playerHealth.CurrentHealth)}", style);

            if (playerMana != null)
            {
                GUI.Label(new Rect(20f, 44f, 400f, 32f),
                    $"Mana {Mathf.CeilToInt(playerMana.CurrentMana)}", style);
            }

            GUI.Label(new Rect(20f, 72f, 700f, 28f),
                "Left-click to move and open doors    Right-click to cast fireball", style);
        }

        private void DrawEndScreen()
        {
            GUI.color = new Color(0f, 0f, 0f, 0.75f);
            GUI.DrawTexture(new Rect(0f, 0f, Screen.width, Screen.height), Texture2D.whiteTexture);
            GUI.color = Color.white;

            var endStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 56,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleCenter,
            };
            endStyle.normal.textColor = won ? new Color(1f, 0.85f, 0.3f) : new Color(1f, 0.35f, 0.35f);

            GUI.Label(new Rect(0f, Screen.height * 0.36f, Screen.width, 80f),
                won ? "YOU ESCAPED" : "YOU DIED", endStyle);

            var hintStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 22,
                alignment = TextAnchor.MiddleCenter,
            };
            hintStyle.normal.textColor = Color.white;
            GUI.Label(new Rect(0f, Screen.height * 0.5f, Screen.width, 40f), "Press R to play again", hintStyle);

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null && keyboard.rKey.wasPressedThisFrame)
            {
                UnityEngine.SceneManagement.SceneManager.LoadScene(
                    UnityEngine.SceneManagement.SceneManager.GetActiveScene().buildIndex);
            }
        }
    }
}
