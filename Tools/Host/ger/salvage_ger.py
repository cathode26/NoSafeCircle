"""Consolidate the 2026-09-14 GER outputs into one salvage folder.

Copies only: every original packet, round and report stays where it is. For each GER task this
writes the round outputs, the refined round-03 contract as JSON, and any owner-patched contract,
then an INDEX.md with outcomes, commits, follow-ups and exact resume steps. It also zips the GER
tooling and copies the overnight report and the NSC-015 decomposition preflight.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import subprocess
import zipfile

import ger_patch

PACKETS_ROOT = pathlib.Path(r"C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER")
OUT = pathlib.Path(r"C:\nscrev\ger-salvage-20260914")
TOOLS = pathlib.Path(r"C:\nscrev\ger-tools")
REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
REPORT = pathlib.Path(r"C:\nscrev\reports\ger-overnight-20260914.md")
D1B2_PREFLIGHT = pathlib.Path(r"C:\nscrev\d1b2-nsc015-5b3d0b3a-preflight.json")
ROUNDS = ["01-codex-generate", "02-claude-evaluate", "03-codex-refine", "04-claude-reaudit",
          "05-owner-patch", "06-claude-recheck"]

# task: (packet, outcome key, commit or None, one-line result)
TASKS = {
    "NSC-044": ("20260914-055357-NSC-044", "committed", "1795df8f", "Revision 4 committed and released."),
    "NSC-017": ("20260914-073054-NSC-017", "committed", "52ffed00", "Revision 4 committed and released."),
    "NSC-052": ("20260914-073309-NSC-052", "committed", "8d485ebd", "Revision 2 committed and released."),
    "NSC-053": ("20260914-073917-NSC-053", "committed", "b25aa5d3", "Revision 3 committed and released."),
    "NSC-054": ("20260914-075919-NSC-054", "committed", "7bd75a9b", "Revision 3 committed and released; since implemented by Codex."),
    "NSC-020": ("20260914-081837-NSC-020", "committed", "d69ad5f7", "Revision 3 committed and released; now needs_replan (new delivery needed)."),
    "NSC-003": ("20260914-083223-NSC-003", "committed", "96a6293c", "Revision 4 committed and released (INT-001 only)."),
    "NSC-015": ("20260914-072839-NSC-015", "committed_held", "6fb702b5", "Revision 6 committed; held, decomposition queued (2 proposed splits)."),
    "NSC-012": ("20260914-080828-NSC-012", "no_change", None, "Released without a contract change."),
    "NSC-041": ("20260914-081321-NSC-041", "no_change", None, "Released without a contract change (Codex chose option 1)."),
    "NSC-005": ("20260914-083819-NSC-005", "no_change", None, "Released without a contract change; evidence packaging route still open."),
    "NSC-045": ("20260914-055406-NSC-045", "needs_design", None, "needs_design: room wall/obstacle decisions."),
    "NSC-046": ("20260914-055414-NSC-046", "needs_design", None, "needs_design: room decisions; D3 moves to (-8,54)."),
    "NSC-047": ("20260914-055422-NSC-047", "room_cascade", None, "blocked_not_design with exact text; must rebase after NSC-046."),
    "NSC-048": ("20260914-055432-NSC-048", "room_cascade", None, "blocked_not_design with exact text; must rebase after NSC-046 and NSC-047."),
    "NSC-007": ("20260914-065058-NSC-007", "needs_design", None, "needs_design: Charged Fireball decisions."),
    "NSC-008": ("20260914-065104-NSC-008", "needs_design", None, "needs_design: Frost Field decisions."),
    "NSC-009": ("20260914-072739-NSC-009", "needs_design", None, "needs_design: Force Wave decisions."),
    "NSC-030": ("20260914-065035-NSC-030", "needs_design", None, "needs_design: encounter placement decisions."),
    "NSC-078": ("20260914-065051-NSC-078", "needs_design", None, "needs_design: prop art pack decisions."),
    "NSC-085": ("20260914-070454-NSC-085", "needs_design", None, "needs_design: expansion wing / GDD scope."),
    "NSC-088": ("20260914-080507-NSC-088", "needs_design", None, "needs_design: five Spectral Decoy decisions."),
    "NSC-004": ("20260914-084042-NSC-004", "partial", None, "Rounds 01-02 done; Codex refine failed on the Codex usage limit."),
    "NSC-066": ("20260914-085155-NSC-066", "partial", None, "Rounds 01-02 done; Codex refine failed on the Codex usage limit."),
}
NOT_STARTED = ["NSC-049", "NSC-071", "NSC-072", "NSC-079", "NSC-080", "NSC-081", "NSC-082", "NSC-083"]

OUTCOME_LABELS = {
    "committed": "Committed and released",
    "committed_held": "Committed, still held (decomposition queued)",
    "no_change": "Released without a contract change",
    "needs_design": "Held: needs Vincent's design decisions",
    "room_cascade": "Held: rebase after NSC-046's room decisions",
    "partial": "Held: cycle cut off by the Codex usage limit",
}

FOLLOW_UPS = [
    "NSC-017 should depend on NSC-053 (NSC-017 disables and re-enables the keep-distance component around a locked-door attack).",
    "NSC-033's enemy-reset work should depend on NSC-053 and NSC-055; it must also call RangedEnemyAttack.ResetAttack (NSC-054 INT-002) and EnemyHealth.ResetHealth from a real zero-health restart.",
    "NSC-049 should record NSC-017 INT-003, and its GER must carry the committed-scene D1-D5 door feedback proof (NSC-041 option 1).",
    "NSC-092's note wrongly says it alone owns logical:enemy-locomotion-behavior-surface; six other tasks lock it.",
    "NSC-052 INT-001 cites NSC-017 revision-3 gate IDs; NSC-017 revision 4 moved the real-enemy breach review to INT-004.",
    "NSC-015's prefab work needs an exactly-once registry/defeat Play Mode gate like NSC-055 VAL-001.",
    "NSC-007, NSC-008 and NSC-009: add insufficient-mana denial gates (PlayerMana.Spend false + CastDenied); fix the missing title-screen/game-entry spell suspend handoff consistently; NSC-007 should repeat NSC-003 INT-001's single movement-restriction rule; Fireball denial timing is NSC-007's design decision.",
    "NSC-005: do not commit a new evidence record until the packaging route is chosen; first check whether its three validated commits are missing from the 2026-08-29 history-identity migration map.",
    "NSC-020: decide holds or revalidation for the reflection-based crossing tests in NSC-050, NSC-051 and NSC-052; check D5 reachability past the Final Room edge at z = 86 (NSC-086).",
    "Room depth cascade: once NSC-046 settles, NSC-047 moves to Z [54,76] with its entry at X -8, and NSC-048 to Z [76,104]; each needs a rebased, re-checked revision.",
    "Minor next-revision wording follow-ups are listed in the 06-claude-recheck.md files: NSC-054 C-01..C-09, NSC-020 C-01..C-04, NSC-003 C-01..C-05, and NSC-044 C-01..C-06.",
]


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def task_title(task_id: str) -> str:
    try:
        return json.loads((REPO / "Tasks" / f"{task_id}.yaml").read_text(encoding="utf-8"))["title"]
    except (OSError, ValueError, KeyError):
        return ""


def salvage_task(task_id: str, packet_name: str) -> list[str]:
    packet = PACKETS_ROOT / packet_name
    target = OUT / "tasks" / task_id
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    if not packet.is_dir():
        return ["PACKET MISSING"]
    for name, dest in (("GER_PACKET.md", "00-ger-packet.md"), ("NODE_STATUS.json", "node-status.json"),
                       ("GER_ADDENDUM.md", "00-ger-addendum.md")):
        if (packet / name).is_file():
            shutil.copy2(packet / name, target / dest)
            copied.append(dest)
    for round_name in ROUNDS:
        output = packet / round_name / "OUTPUT.md"
        if output.is_file():
            shutil.copy2(output, target / f"{round_name}.md")
            copied.append(f"{round_name}.md")
    refine = packet / "03-codex-refine" / "OUTPUT.md"
    if refine.is_file():
        try:
            contract = ger_patch.final_contract(refine.read_text(encoding="utf-8"))
            (target / "03-refined-contract.json").write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            copied.append("03-refined-contract.json")
        except (ValueError, json.JSONDecodeError) as error:
            copied.append(f"(round-03 contract not extractable: {error})")
    patched = packet / "05-owner-patch" / "PATCHED_CONTRACT.json"
    if patched.is_file():
        shutil.copy2(patched, target / "05-patched-contract.json")
        copied.append("05-patched-contract.json")
    return copied


def zip_tools() -> pathlib.Path:
    destination = OUT / "tooling" / "ger-tools-20260914.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(TOOLS.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(TOOLS.parent))
    return destination


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, missing = [], []
    for task_id, (packet, outcome, commit, result) in TASKS.items():
        files = salvage_task(task_id, packet)
        if files == ["PACKET MISSING"]:
            missing.append(f"{task_id} ({packet})")
        rows.append((task_id, task_title(task_id), outcome, commit, packet, result, files))
    tools_zip = zip_tools()
    (OUT / "report").mkdir(exist_ok=True)
    shutil.copy2(REPORT, OUT / "report" / REPORT.name)
    if D1B2_PREFLIGHT.is_file():
        (OUT / "nsc015-d1b2").mkdir(exist_ok=True)
        shutil.copy2(D1B2_PREFLIGHT, OUT / "nsc015-d1b2" / "offline-preflight.json")

    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    ahead = git("rev-list", "--count", "origin/main..main")
    superseded = sorted(p.name for p in PACKETS_ROOT.glob("2026*-NSC-*")
                        if p.is_dir() and p.name not in {v[0] for v in TASKS.values()})

    lines = [
        "# GER salvage, 2026-09-14",
        "",
        f"Created {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC after Vincent stopped GER because the Codex usage limit ran out.",
        "Everything here is a copy. The original packets stay under `Downloads\\NoSafeCircleOutput\\RoomContentGER`.",
        "",
        "## Repository backup",
        "",
        f"- Local `main`: `{head}`. `origin/main`: `{origin}`. Local main is **{ahead} commits ahead** and not pushed.",
        "- Full-history bundle: `git/NoSafeCircle-main-96a6293c.bundle`. Restore with `git clone <bundle> <dir>` or `git fetch <bundle> main`.",
        "",
        "## Tasks",
        "",
        "| Task | Title | Outcome | Commit | Result | Salvaged files |",
        "|---|---|---|---|---|---|",
    ]
    for task_id, title, outcome, commit, packet, result, files in sorted(rows, key=lambda r: (list(OUTCOME_LABELS).index(r[2]), r[0])):
        lines.append(f"| {task_id} | {title} | {OUTCOME_LABELS[outcome]} | {('`' + commit + '`') if commit else ''} | {result} | "
                     f"`tasks/{task_id}/`: {len([f for f in files if not f.startswith('(')])} files |")
    lines += [
        "",
        f"**Not started (held until the room decisions land):** {', '.join(NOT_STARTED)}.",
        "",
        "## What each folder holds",
        "",
        "- `00-ger-packet.md`: the task brief GER started from. `00-ger-addendum.md`: the category guidance used.",
        "- `01-codex-generate.md` to `04-claude-reaudit.md`: the four GER rounds. The re-audit holds the findings, exact replacement text and the questions for Vincent.",
        "- `03-refined-contract.json`: the refined contract proposed in round 03, ready to reuse.",
        "- `05-owner-patch.md`, `05-patched-contract.json`, `06-claude-recheck.md`: owner patch and fresh re-check, where a commit went through them.",
        "",
        "## How to pick each group up later",
        "",
        "- **Needs design:** after Vincent answers, run a fresh GER cycle and pass his answers plus the salvaged re-audit as `--feedback-file`, so the next cycle starts from `03-refined-contract.json` and the ready non-design fixes.",
        "- **Room cascade (NSC-047, NSC-048):** rebase their coordinates onto NSC-046's settled layout, then apply the exact blocker text from their re-audits and re-check.",
        "- **Cut off by Codex (NSC-004, NSC-066):** once Codex usage returns, rename the failed `03-codex-refine` in the original packet to `03-codex-refine.failed-<UTC>`, then run `python -B ger_node.py <ID> --existing-packet <packet> --context <recorded context> --addendum-file <packet>/GER_ADDENDUM.md`. Rounds 01 and 02 are reused.",
        "- **NSC-015 decomposition:** a clean clone of local main at `5b3d0b3a` passed the zero-cost preflight (`nsc015-d1b2/offline-preflight.json`). The paid review-only run needs Vincent's go and Codex usage; see the overnight report, question 66.",
        "",
        "## Graph follow-ups found by GER (not applied)",
        "",
    ]
    lines += [f"- {item}" for item in FOLLOW_UPS]
    lines += [
        "",
        "## Also in this folder",
        "",
        f"- `report/{REPORT.name}`: the overnight report with all 88 numbered questions.",
        f"- `tooling/{tools_zip.name}`: the GER tools (round runner, node driver, owner patch, contract apply, watcher, addenda, #127 post bodies).",
        "",
        "## Superseded packets (not copied)",
        "",
        ", ".join(f"`{name}`" for name in superseded) or "none",
    ]
    if missing:
        lines += ["", "## Missing packets", "", ", ".join(missing)]
    (OUT / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(json.dumps({"out": str(OUT), "tasks": len(rows), "missing": missing, "files": total,
                      "ahead_of_origin": ahead, "tools_zip_bytes": tools_zip.stat().st_size}, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
