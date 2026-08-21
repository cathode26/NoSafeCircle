from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GDD = ROOT / "Docs" / "GDD" / "No_Safe_Circle_GDD.md"


def main() -> int:
    text = GDD.read_text(encoding="utf-8")

    old_action = "| Frost Field | Place a temporary area that heavily slows enemies. | Divides crowds and protects routes. |"
    new_action = "| Frost Field | Place a temporary area at the current cursor world-space target that heavily slows enemies. Frost Field consumes the shared pointer target exposed by Player Movement rather than projecting screen coordinates independently. | Divides crowds and protects routes. |"

    if new_action not in text:
        if old_action not in text:
            raise RuntimeError("Could not find Frost Field action row to clarify.")
        text = text.replace(old_action, new_action, 1)

    old_feedback = "- Frost Field feedback: The Frost Field cast and active field provide player-facing feedback that makes the effect readable while it is being placed/used. The exact visual or audio treatment is an implementation choice."
    new_feedback = "- Frost Field targeting and feedback: Frost Field is placed at the current shared world-space pointer target exposed by Player Movement. Frost Field does not independently project screen coordinates. The cast and active field provide player-facing feedback that makes the targeted placement and active effect readable while it is being placed/used. The exact visual or audio treatment is an implementation choice."

    if new_feedback not in text:
        if old_feedback not in text:
            raise RuntimeError("Could not find Frost Field feedback rule to clarify.")
        text = text.replace(old_feedback, new_feedback, 1)

    GDD.write_text(text, encoding="utf-8")
    print("Clarified Frost Field cursor-target placement in the GDD.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
