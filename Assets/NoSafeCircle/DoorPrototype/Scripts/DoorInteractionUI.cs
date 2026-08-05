using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    public class DoorInteractionUI : MonoBehaviour
    {
        [SerializeField] private DoorInteractable door;
        [SerializeField] private GameObject promptRoot;
        [SerializeField] private Image progressFillImage;

        private void Update()
        {
            if (door == null) return;

            if (promptRoot != null)
            {
                promptRoot.SetActive(door.IsPlayerInRange && !door.IsOpen);
            }

            if (progressFillImage != null)
            {
                progressFillImage.fillAmount = door.Progress;
            }
        }
    }
}
