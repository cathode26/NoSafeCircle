# Third-party Unity dependencies

This inventory records the libraries added for NSC-057. It establishes the exact
source and repository files for review. Vincent approved both exact sources
and their licenses for this course project on 2026-09-14 (NSC-057 VAL-001).

| Library | Exact source | Repository placement | License and review state |
| --- | --- | --- | --- |
| deVoid Signals | [`yankooliveira/signals` commit `b1969caa712635c1b469a75b2946a31fc79737bb`](https://github.com/yankooliveira/signals/tree/b1969caa712635c1b469a75b2946a31fc79737bb); `Signals.cs` Git blob `1fd9dba403f4a19f0dd6af17518d7b4518a0433c`, SHA-256 `dcc55c39f5183786e51d33743700b8b9107d36adaa16ca8fc04bc29669716da1` | `Assets/Plugins/deVoid/Signals/Signals.cs` (upstream bytes), original MIT text at `Assets/Plugins/deVoid/Signals/LICENSE.txt`, plus project-authored `deVoid.Signals.asmdef` | [MIT license](https://github.com/yankooliveira/signals/blob/b1969caa712635c1b469a75b2946a31fc79737bb/LICENSE); approved by Vincent 2026-09-14. |
| DOTween Standard | [Demigiant official v1.3.030 download](https://dotween.demigiant.com/download), June 23, 2026; downloaded ZIP SHA-256 `62a0ececd274e1587eb0dea15f3afab392fbda5a0f8cac7287fbf7f64925a1ba`, matching a fresh download from the official URL | The official 28-path Unity package was imported under `Assets/Plugins/Demigiant/DOTween/`; interactive setup removed its six one-time Upgrade Manager paths. The remaining plugin files include the original `readme.txt`; project settings are in `Assets/Resources/DOTweenSettings.asset`. | [DOTween Standard license](https://dotween.demigiant.com/license.php), distinct from DOTween Pro; approved by Vincent 2026-09-14. |

The remaining DOTween package files and deVoid source/license retain their
upstream bytes. The Signals
assembly definition and its reference from `NoSafeCircle.DoorPrototype.asmdef`
are No Safe Circle configuration. DOTween's standard plugin DLL is automatically
referenced by Unity. On its first Unity import, DOTween added the `DOTWEEN`
scripting define to the project build targets in
`ProjectSettings/ProjectSettings.asset`. Unity also generated the previously
missing `Assets/NoSafeCircle/DoorPrototype/Scripts/Enemies.meta` for an
existing folder; that stable folder GUID is retained so later imports do not
create it again. No Pro package, Addressables package, or other dependency
was added. Vincent completed DOTween's interactive Utility Panel setup in
Unity 6000.1.8f1 on 2026-09-14. It created `DOTweenSettings.asset`, removed
the six one-time Upgrade Manager files, and added `DOTWEEN_UITOOLKIT` beside
the existing `DOTWEEN` define. The setup enabled the built-in audio, physics,
2D physics, sprite, UI, and UI Toolkit modules and left external-asset modules
disabled. Focused regression after this setup still needs verification.

Adding these libraries makes their APIs available; it does not require gameplay
systems to use them. New code should follow the selection rules in
`ENGINEERING_STANDARDS.md` rather than adding another event bus or tween tool.
