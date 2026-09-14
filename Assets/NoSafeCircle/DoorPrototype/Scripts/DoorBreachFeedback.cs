using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    /// Presents the consequence of accepted damage against a locked door. The door owns
    /// durability and acceptance; this component owns the authored cracks, indicator, and
    /// transient hit feedback. All references are explicit so generated scenes and tests can
    /// wire the same component without relying on hierarchy searches.
    [DisallowMultipleComponent]
    public sealed class DoorBreachFeedback : MonoBehaviour
    {
        [SerializeField] private DoorInteractable door;
        [SerializeField] private Transform shakeTarget;
        [SerializeField] private GameObject durabilityIndicator;
        [SerializeField] private Image durabilityFill;
        [SerializeField] private GameObject[] crackStages;
        [SerializeField] private AudioSource bangAudio;
        [SerializeField] private float shakeDuration = 0.18f;
        [SerializeField] private float shakeMagnitude = 0.06f;

        private Vector3 originalLocalPosition;
        private float shakeTimeRemaining;
        private static AudioClip generatedBangClip;

        public float DurabilityRatio => durabilityFill == null ? 0f : durabilityFill.fillAmount;
        public bool IsShaking => shakeTimeRemaining > 0f;

        private void Awake()
        {
            if (door == null) door = GetComponent<DoorInteractable>();
            if (shakeTarget == null) shakeTarget = transform;
            originalLocalPosition = shakeTarget.localPosition;
        }

        private void OnEnable()
        {
            if (door != null) door.DamageTaken += HandleDamageTaken;
            if (door != null) door.Broken += HandleBroken;
            if (door != null) door.ResetCompleted += ResetFeedback;
            RefreshFromDoor();
            EnsureBangClip();
        }

        private void OnDisable()
        {
            if (door != null) door.DamageTaken -= HandleDamageTaken;
            if (door != null) door.Broken -= HandleBroken;
            if (door != null) door.ResetCompleted -= ResetFeedback;
            CancelShake();
            StopBang();
        }

        private void Update()
        {
            if (shakeTimeRemaining <= 0f || shakeTarget == null) return;
            shakeTimeRemaining -= Time.deltaTime;
            var phase = shakeTimeRemaining * 70f;
            shakeTarget.localPosition = originalLocalPosition + new Vector3(Mathf.Sin(phase), 0f, 0f) * shakeMagnitude;
            if (shakeTimeRemaining <= 0f) CancelShake();
        }

        public void Bind(DoorInteractable target, Transform targetToShake, Image fill, GameObject[] cracks,
            AudioSource bangSource = null, GameObject indicatorObject = null)
        {
            if (door != null) door.DamageTaken -= HandleDamageTaken;
            if (door != null) door.Broken -= HandleBroken;
            if (door != null) door.ResetCompleted -= ResetFeedback;
            door = target;
            shakeTarget = targetToShake == null ? transform : targetToShake;
            durabilityIndicator = indicatorObject;
            durabilityFill = fill;
            crackStages = cracks;
            bangAudio = bangSource;
            originalLocalPosition = shakeTarget.localPosition;
            if (isActiveAndEnabled && door != null)
            {
                door.DamageTaken += HandleDamageTaken;
                door.Broken += HandleBroken;
                door.ResetCompleted += ResetFeedback;
            }
            RefreshFromDoor();
            EnsureBangClip();
        }

        public void ResetFeedback()
        {
            CancelShake();
            StopBang();
            if (durabilityFill != null) durabilityFill.fillAmount = 1f;
            if (durabilityIndicator != null) durabilityIndicator.SetActive(false);
            SetCrackStage(-1);
        }

        private void HandleDamageTaken(float amount)
        {
            RefreshFromDoor();
            shakeTimeRemaining = shakeDuration;
            EnsureBangClip();
            bangAudio?.Play();
        }

        private void HandleBroken()
        {
            RefreshFromDoor();
            CancelShake();
        }

        private void RefreshFromDoor()
        {
            if (door == null) return;
            var ratio = door.MaxDurability > 0f ? Mathf.Clamp01(door.CurrentDurability / door.MaxDurability) : 0f;
            if (durabilityFill != null) durabilityFill.fillAmount = ratio;
            if (durabilityIndicator != null)
                durabilityIndicator.SetActive(door.IsLocked && ratio > 0f && ratio < 1f);
            var stage = crackStages == null || crackStages.Length == 0
                ? -1
                : Mathf.Clamp(Mathf.CeilToInt((1f - ratio) * crackStages.Length) - 1, -1, crackStages.Length - 1);
            SetCrackStage(stage);
        }

        private void SetCrackStage(int activeStage)
        {
            if (crackStages == null) return;
            for (var i = 0; i < crackStages.Length; i++)
                if (crackStages[i] != null) crackStages[i].SetActive(i <= activeStage);
        }

        private void CancelShake()
        {
            shakeTimeRemaining = 0f;
            if (shakeTarget != null) shakeTarget.localPosition = originalLocalPosition;
        }

        private void StopBang()
        {
            if (bangAudio != null) bangAudio.Stop();
        }

        // The scene builder saves the AudioSource, while this short synthesized impact exists
        // only during play. No generated AudioClip asset or third-party sound is needed.
        private void EnsureBangClip()
        {
            if (!Application.isPlaying || bangAudio == null || bangAudio.clip != null) return;
            if (generatedBangClip == null)
            {
                const int sampleRate = 22050;
                const int sampleCount = sampleRate / 4;
                var samples = new float[sampleCount];
                uint noiseState = 0x52c052u;
                for (var i = 0; i < samples.Length; i++)
                {
                    var time = i / (float)sampleRate;
                    noiseState = unchecked(noiseState * 1664525u + 1013904223u);
                    var grit = ((noiseState >> 16) & 0x7fffu) / 16384f - 1f;
                    var thud = Mathf.Sin(2f * Mathf.PI * (90f * time - 35f * time * time));
                    samples[i] = 0.72f * Mathf.Exp(-22f * time) * (0.8f * thud + 0.2f * grit);
                }

                generatedBangClip = AudioClip.Create("Door breach bang", sampleCount, 1, sampleRate, false);
                generatedBangClip.hideFlags = HideFlags.DontSave;
                generatedBangClip.SetData(samples, 0);
            }

            bangAudio.clip = generatedBangClip;
        }
    }
}
