using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    public class PlayerHealthUI : MonoBehaviour
    {
        [SerializeField] private PlayerHealth health;
        [SerializeField] private Image fillImage;

        private PlayerHealth subscribedHealth;

        private void OnEnable()
        {
            Bind(health, fillImage);
        }

        private void OnDisable()
        {
            Unsubscribe();
        }

        public void Bind(PlayerHealth source, Image target)
        {
            Unsubscribe();
            health = source;
            fillImage = target;
            subscribedHealth = health;
            if (subscribedHealth != null)
            {
                subscribedHealth.HealthChanged += HandleHealthChanged;
            }

            RefreshFill();
        }

        private void Unsubscribe()
        {
            if (subscribedHealth != null)
            {
                subscribedHealth.HealthChanged -= HandleHealthChanged;
                subscribedHealth = null;
            }
        }

        private void HandleHealthChanged(float currentHealth)
        {
            RefreshFill();
        }

        private void RefreshFill()
        {
            if (health == null || fillImage == null) return;

            fillImage.fillAmount = health.MaxHealth > 0f ? health.CurrentHealth / health.MaxHealth : 0f;
        }
    }
}
