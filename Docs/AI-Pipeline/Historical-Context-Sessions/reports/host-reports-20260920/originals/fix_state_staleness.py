"""Correct the three entries in the Game Agent state file that went stale during the session."""
import io

path = r'C:\NSC\agent-state\game-agent.md'
data = io.open(path, encoding='utf-8', newline='').read()

fixes = [
    (
        "1. **`C:\\nscrev\\reports\\land-nsc069-evidence.ps1`** - fast-forwards main to the NSC-069 evidence\n"
        "   commit. **This is the one that unblocks the five room tasks.**\n",
        "1. ~~NSC-069 fast-forward~~ **LANDED.** Main is `91a415ab9`, NSC-069 reads **conformant**, and\n"
        "   the five rooms are dispatchable. Still owed: `nsc_viewer.py uncomplete NSC-069` (Viewer\n"
        "   Agent's lane) and the SuccessfullTasks archive.\n",
    ),
    (
        "## NSC-069: DONE, awaiting the fast-forward",
        "## NSC-069: DONE and landed on main",
    ),
    (
        "(parent is main `e3a742142`), reads **conformant** there.",
        "is on canonical main; `taskcontrol state NSC-069` reads **conformant**, finding\n"
        "`approved_delivery_selected`.",
    ),
    (
        "- My conditions in the contract: one atlas for wall sprites; a wall-occlusion test with a character\n"
        "  in front of and behind the same tile; kit regenerated at `tile_size 90` rather than nudging\n"
        "  `orthographicSize` (Vincent agreed).",
        "- My conditions in the contract: one atlas for wall sprites; a wall-occlusion test with a character\n"
        "  in front of and behind the same tile.\n"
        "- **Camera: Vincent chose `orthographicSize` 8 -> 7.9551 with the 96 px kit**, reversing my earlier\n"
        "  advice. I had recommended regenerating the kit instead, then found regenerating does **not** fix\n"
        "  the stride: at size 8 a cell is 95.459 px at 1080p and 127.279 at 1440p, so pixel-snapped wall\n"
        "  runs alternate 48/47 px. At 7.9551 cells are exactly 96 and 128. The stride is a property of the\n"
        "  cell and camera, not of the art, which is why regenerating could never have fixed it. My six\n"
        "  re-checks are contract requirements in NSC-064, and the value must be a derived constant with its\n"
        "  derivation in a comment, never a bare `7.9551f`.\n"
        "- **NSC-064 claims every file it edits**, including the two previously unclaimed test files: the\n"
        "  constant and its assertions must move in one commit or main is red between them. Only the\n"
        "  `orthographicSize` assertion in `DoorPrototypeSceneBuilderTests.cs` may change - five other\n"
        "  tasks' assertions live in that file.",
    ),
]

for old, new in fixes:
    if old in data:
        data = data.replace(old, new, 1)
    else:
        print('MISSED anchor: %r' % old.splitlines()[0][:70])

io.open(path, 'w', encoding='utf-8', newline='').write(data)
print('state file corrected')
