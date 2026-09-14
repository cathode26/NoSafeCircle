# Third-party Unity dependencies

This inventory records the libraries added for NSC-057. It establishes the exact
source and repository files for review; the developer's course-use and license
confirmation required by NSC-057 VAL-001 remains pending.

| Library | Exact source | Repository placement | License and review state |
| --- | --- | --- | --- |
| deVoid Signals | [`yankooliveira/signals` commit `b1969caa712635c1b469a75b2946a31fc79737bb`](https://github.com/yankooliveira/signals/tree/b1969caa712635c1b469a75b2946a31fc79737bb); `Signals.cs` Git blob `1fd9dba403f4a19f0dd6af17518d7b4518a0433c`, SHA-256 `dcc55c39f5183786e51d33743700b8b9107d36adaa16ca8fc04bc29669716da1` | `Assets/Plugins/deVoid/Signals/Signals.cs` (upstream bytes), original MIT text at `Assets/Plugins/deVoid/Signals/LICENSE.txt`, plus project-authored `deVoid.Signals.asmdef` | [MIT license](https://github.com/yankooliveira/signals/blob/b1969caa712635c1b469a75b2946a31fc79737bb/LICENSE); developer confirmation pending. |
| DOTween Standard | [Demigiant official v1.3.030 download](https://dotween.demigiant.com/download), June 23, 2026; downloaded ZIP SHA-256 `62a0ececd274e1587eb0dea15f3afab392fbda5a0f8cac7287fbf7f64925a1ba`, matching a fresh download from the official URL | All 28 asset paths from `DOTween_1_3_030.unityPackage` under `Assets/Plugins/Demigiant/DOTween/`, including its original `readme.txt` and Unity `.meta` files | [DOTween Standard license](https://dotween.demigiant.com/license.php), distinct from DOTween Pro; developer confirmation pending. |

The DOTween package files and deVoid source/license are unchanged. The Signals
assembly definition and its reference from `NoSafeCircle.DoorPrototype.asmdef`
are No Safe Circle configuration. DOTween's standard plugin DLL is automatically
referenced by Unity; no Pro package, Addressables package, or other dependency
was added. The DOTween Utility Panel's setup step and Unity 6000.1.8f1 compile
and regression results must be checked before NSC-057 is accepted.

Adding these libraries makes their APIs available; it does not require gameplay
systems to use them. New code should follow the selection rules in
`ENGINEERING_STANDARDS.md` rather than adding another event bus or tween tool.
