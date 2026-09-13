using System;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    public readonly struct ConfirmedWizardSelection : IEquatable<ConfirmedWizardSelection>
    {
        public ConfirmedWizardSelection(WizardPresentation presentation, WizardSkin skin)
        {
            if (!Enum.IsDefined(typeof(WizardPresentation), presentation))
                throw new ArgumentOutOfRangeException(nameof(presentation));
            if (!Enum.IsDefined(typeof(WizardSkin), skin))
                throw new ArgumentOutOfRangeException(nameof(skin));

            Presentation = presentation;
            Skin = skin;
        }

        public WizardPresentation Presentation { get; }
        public WizardSkin Skin { get; }

        public bool Equals(ConfirmedWizardSelection other)
        {
            return Presentation == other.Presentation && Skin == other.Skin;
        }

        public override bool Equals(object obj)
        {
            return obj is ConfirmedWizardSelection other && Equals(other);
        }

        public override int GetHashCode()
        {
            return ((int)Presentation * 397) ^ (int)Skin;
        }

        public override string ToString()
        {
            return $"{Presentation}/{Skin}";
        }
    }

    [Serializable]
    public sealed class WizardSelectionOptionBinding
    {
        [SerializeField] private WizardPresentation presentation;
        [SerializeField] private WizardSkin skin;
        [SerializeField] private Button button;
        [SerializeField] private Image previewImage;
        [SerializeField] private Text label;
        [SerializeField] private GameObject selectedIndicator;

        public WizardPresentation Presentation => presentation;
        public WizardSkin Skin => skin;
        public Button Button => button;
        public Sprite PreviewSprite => previewImage != null ? previewImage.sprite : null;
        public string Label => label != null ? label.text : string.Empty;
        public bool IsSelected => selectedIndicator != null && selectedIndicator.activeSelf;

        public bool IsComplete =>
            Enum.IsDefined(typeof(WizardPresentation), presentation) &&
            Enum.IsDefined(typeof(WizardSkin), skin) &&
            button != null &&
            previewImage != null &&
            previewImage.sprite != null &&
            label != null &&
            !string.IsNullOrWhiteSpace(label.text) &&
            selectedIndicator != null;

        internal void SetSelected(bool isSelected)
        {
            if (selectedIndicator != null)
            {
                selectedIndicator.SetActive(isSelected);
            }
        }
    }
}
