using System;
using UnityEngine;
using UnityEngine.UI;

namespace NoSafeCircle.DoorPrototype
{
    public sealed class WizardSelectionController : MonoBehaviour
    {
        private const int RequiredOptionCount = 4;

        [SerializeField] private TitleScreenController titleScreenController;
        [SerializeField] private GameObject selectionPanel;
        [SerializeField] private Button confirmButton;
        [SerializeField] private WizardSelectionOptionBinding[] options;

        private int selectedOptionIndex = -1;
        private ConfirmedWizardSelection? confirmedSelection;

        public int OptionCount => options != null ? options.Length : 0;
        public int SelectedOptionIndex => selectedOptionIndex;
        public bool IsSelectionVisible => selectionPanel != null && selectionPanel.activeSelf;
        public bool IsConfirmationAvailable => confirmButton != null && confirmButton.interactable;
        public ConfirmedWizardSelection? ConfirmedSelection => confirmedSelection;
        public bool HasValidOptionCatalog => ValidateOptionCatalog();

        /// <summary>
        /// The single confirmed-selection handoff consumed by NSC-068.
        /// </summary>
        public event Action<ConfirmedWizardSelection> WizardSelectionConfirmed;

        private void Awake()
        {
            selectedOptionIndex = -1;
            confirmedSelection = null;

            if (selectionPanel != null)
            {
                selectionPanel.SetActive(false);
            }

            SetConfirmationAvailable(false);
            MarkSelectedOption(-1);

            if (!HasValidOptionCatalog)
            {
                Debug.LogError("WizardSelectionController requires one complete binding for each of the four " +
                    "NSC-062 wizard presentation and skin combinations.", this);
            }
        }

        private void OnEnable()
        {
            if (titleScreenController != null)
            {
                titleScreenController.WizardSelectionRequested += OnWizardSelectionRequested;
            }
        }

        private void OnDisable()
        {
            if (titleScreenController != null)
            {
                titleScreenController.WizardSelectionRequested -= OnWizardSelectionRequested;
            }
        }

        public WizardSelectionOptionBinding GetOption(int index)
        {
            if (options == null || index < 0 || index >= options.Length)
                throw new ArgumentOutOfRangeException(nameof(index));

            return options[index];
        }

        public void SelectOption(int optionIndex)
        {
            if (!IsSelectionVisible || confirmedSelection.HasValue || !HasValidOptionCatalog) return;
            if (optionIndex < 0 || optionIndex >= options.Length) return;

            selectedOptionIndex = optionIndex;
            MarkSelectedOption(optionIndex);
            SetConfirmationAvailable(true);
        }

        public void ConfirmSelection()
        {
            if (!IsSelectionVisible || confirmedSelection.HasValue) return;
            if (selectedOptionIndex < 0 || selectedOptionIndex >= OptionCount) return;

            WizardSelectionOptionBinding option = options[selectedOptionIndex];
            if (option == null || !option.IsComplete) return;

            ConfirmedWizardSelection handoff =
                new ConfirmedWizardSelection(option.Presentation, option.Skin);
            confirmedSelection = handoff;
            SetConfirmationAvailable(false);
            selectionPanel.SetActive(false);
            WizardSelectionConfirmed?.Invoke(handoff);
        }

        private void OnWizardSelectionRequested()
        {
            if (confirmedSelection.HasValue || !HasValidOptionCatalog) return;

            selectedOptionIndex = -1;
            MarkSelectedOption(-1);
            SetConfirmationAvailable(false);
            selectionPanel.SetActive(true);
        }

        private bool ValidateOptionCatalog()
        {
            if (options == null || options.Length != RequiredOptionCount) return false;

            var combinationMask = 0;
            foreach (WizardSelectionOptionBinding option in options)
            {
                if (option == null || !option.IsComplete) return false;

                var combinationIndex = ((int)option.Presentation * 2) + (int)option.Skin;
                if (combinationIndex < 0 || combinationIndex >= RequiredOptionCount) return false;

                var combinationBit = 1 << combinationIndex;
                if ((combinationMask & combinationBit) != 0) return false;
                combinationMask |= combinationBit;
            }

            return combinationMask == (1 << RequiredOptionCount) - 1;
        }

        private void MarkSelectedOption(int selectedIndex)
        {
            if (options == null) return;

            for (var index = 0; index < options.Length; index++)
            {
                options[index]?.SetSelected(index == selectedIndex);
            }
        }

        private void SetConfirmationAvailable(bool isAvailable)
        {
            if (confirmButton != null)
            {
                confirmButton.interactable = isAvailable;
            }
        }
    }
}
