using System;
using System.Collections.Generic;
using NoSafeCircle.DoorPrototype.Content;
using UnityEditor;
using UnityEditor.AddressableAssets;
using UnityEditor.AddressableAssets.Settings;
using UnityEditor.AddressableAssets.Settings.GroupSchemas;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Editor.Content
{
    /// <summary>
    /// One menu item that creates the Addressables settings, the lifetime groups, the labels and the
    /// family folder entries - each ONLY if it does not already exist.
    /// </summary>
    /// <remarks>
    /// <para>
    /// CREATE-ONLY IS THE RULE, AND IT IS THE WHOLE DIFFERENCE BETWEEN THIS BUTTON AND THE BAKE. This
    /// tool may create an asset that is absent and must NEVER overwrite, move, relabel or re-address one
    /// that is present. A bake regenerates its output every run, so the output is never anyone's to
    /// edit and every run is a merge conflict waiting to happen; Vincent's button ran once, made what
    /// was missing, and left what a person had since changed exactly as they left it. Every branch
    /// below asks "is it there?" and does nothing when the answer is yes - including for an entry that
    /// exists in the wrong group with the wrong labels, because "wrong" is a judgement this tool is not
    /// allowed to make.
    /// </para>
    /// <para>
    /// GROUPS ARE LIFETIMES, NOT FOLDERS. ENGINEERING_STANDARDS 8.7: "Group assets by shared lifetime
    /// and dependency behavior. Do not mirror the folder tree blindly." The Props folder joins the
    /// Environment group because a prop lives and dies with the room around it; Data and Ui load at
    /// bootstrap and stay. The Spawners group is created empty: the spawner prefabs are
    /// <c>GameBootstrap</c>'s and still live under Resources, so that lane decides where they move.
    /// </para>
    /// <para>
    /// EVERY ENTRY CARRIES A PLATFORM CLASSIFICATION. 8.7: "Missing platform classification fails
    /// validation." It is the <see cref="ContentId.SharedPlatformLabel"/> on the folder entry, which a
    /// folder entry passes to everything under it - and everything No Safe Circle owns today is
    /// genuinely shared, so that is the only classification this tool ever writes. A platform tree
    /// (<c>Content/WebGL/...</c>) is a separate folder entry in a separate group when one exists.
    /// </para>
    /// </remarks>
    public static class AddressablesSetup
    {
        public const string MenuPath = "No Safe Circle/Content/Create Addressables Settings And Groups";

        private readonly struct GroupSpec
        {
            public GroupSpec(string name, string lifetimeLabel, params ContentId.Family[] families)
            {
                Name = name;
                LifetimeLabel = lifetimeLabel;
                Families = families;
            }

            public string Name { get; }

            public string LifetimeLabel { get; }

            public ContentId.Family[] Families { get; }
        }

        private static readonly GroupSpec[] Groups =
        {
            new GroupSpec("Environment", ContentId.LevelLabel, ContentId.Family.Environment, ContentId.Family.Props),
            new GroupSpec("Gameplay", ContentId.LevelLabel, ContentId.Family.Gameplay),
            new GroupSpec("Ui", ContentId.ApplicationLabel, ContentId.Family.Ui),
            new GroupSpec("Data", ContentId.ApplicationLabel, ContentId.Family.Data),
            new GroupSpec("Spawners", ContentId.ApplicationLabel)
        };

        [MenuItem(MenuPath)]
        public static void CreateMissing()
        {
            Debug.Log(nameof(AddressablesSetup) + ":\n" + Run());
        }

        /// <summary>Creates whatever is absent and reports one line per item, present or created.</summary>
        public static string Run()
        {
            var report = new List<string>();
            AddressableAssetSettings settings = EnsureSettings(report);
            EnsureLabels(settings, report);

            foreach (GroupSpec spec in Groups)
            {
                AddressableAssetGroup group = EnsureGroup(settings, spec.Name, report);
                foreach (ContentId.Family family in spec.Families)
                {
                    string[] labels = { ContentId.FamilyLabel(family), spec.LifetimeLabel, ContentId.SharedPlatformLabel };
                    EnsureFolderEntry(settings, group, ContentId.FolderPath(family), ContentId.FolderName(family),
                        labels, report);
                }
            }

            settings.SetDirty(AddressableAssetSettings.ModificationEvent.BatchModification, null, true, true);
            AssetDatabase.SaveAssets();
            return string.Join("\n", report);
        }

        private static AddressableAssetSettings EnsureSettings(List<string> report)
        {
            bool existed = AddressableAssetSettingsDefaultObject.SettingsExists;
            AddressableAssetSettings settings = AddressableAssetSettingsDefaultObject.GetSettings(true);
            if (settings == null)
            {
                throw new InvalidOperationException("Addressables settings could not be loaded or created. "
                    + "The Editor may still be importing or compiling; run the menu item again afterwards.");
            }

            report.Add((existed ? "present " : "CREATED ") + AddressableAssetSettingsDefaultObject.kDefaultConfigFolder
                + "/" + AddressableAssetSettingsDefaultObject.kDefaultConfigAssetName);
            return settings;
        }

        private static void EnsureLabels(AddressableAssetSettings settings, List<string> report)
        {
            var wanted = new List<string> { ContentId.ApplicationLabel, ContentId.LevelLabel, ContentId.SharedPlatformLabel };
            foreach (ContentId.Family family in Enum.GetValues(typeof(ContentId.Family)))
            {
                wanted.Add(ContentId.FamilyLabel(family));
            }

            List<string> existing = settings.GetLabels();
            foreach (string label in wanted)
            {
                if (existing.Contains(label))
                {
                    report.Add("present label '" + label + "'");
                    continue;
                }

                settings.AddLabel(label, false);
                report.Add("CREATED label '" + label + "'");
            }
        }

        private static AddressableAssetGroup EnsureGroup(AddressableAssetSettings settings, string name, List<string> report)
        {
            AddressableAssetGroup group = settings.FindGroup(name);
            if (group != null)
            {
                report.Add("present group '" + name + "'");
                return group;
            }

            group = settings.CreateGroup(name, false, false, false, null,
                typeof(BundledAssetGroupSchema), typeof(ContentUpdateGroupSchema));

            // Only on a group this run made: local build and load paths, the Addressables defaults for
            // content that ships inside the player. A pre-existing group keeps whatever it has.
            BundledAssetGroupSchema bundled = group.GetSchema<BundledAssetGroupSchema>();
            bundled.BuildPath.SetVariableByName(settings, AddressableAssetSettings.kLocalBuildPath);
            bundled.LoadPath.SetVariableByName(settings, AddressableAssetSettings.kLocalLoadPath);
            report.Add("CREATED group '" + name + "' (local build and load paths)");
            return group;
        }

        private static void EnsureFolderEntry(AddressableAssetSettings settings, AddressableAssetGroup group,
            string folderPath, string address, string[] labels, List<string> report)
        {
            if (!AssetDatabase.IsValidFolder(folderPath))
            {
                report.Add("absent  " + folderPath + " (no folder yet, so no entry; run again once it exists)");
                return;
            }

            string guid = AssetDatabase.AssetPathToGUID(folderPath);
            if (settings.FindAssetEntry(guid) != null)
            {
                report.Add("present entry for " + folderPath + " (left exactly as it is)");
                return;
            }

            AddressableAssetEntry entry = settings.CreateOrMoveEntry(guid, group, false, false);
            entry.address = address;
            foreach (string label in labels)
            {
                entry.SetLabel(label, true, true, false);
            }

            report.Add("CREATED entry '" + address + "' -> group '" + group.Name + "' [" + string.Join(", ", labels) + "]");
        }
    }
}
