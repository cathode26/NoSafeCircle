# GER Orchestrator contract decisions (2026-09-16 / 2026-09-17)

## These are dated records. They are not standing authority.

Each file here records the design decisions the GER Orchestrator made for **one named revision** of
one or more task contracts, on the date in its own header. A contract has moved on since: every
contract cited below is now several revisions further forward.

**The current authority for any task is `Tasks/NSC-###.yaml` at main.** If a statement here
disagrees with the contract, the contract wins, and this file is simply a record of what was
decided at the revision it names.

That sentence is the whole reason this README exists. On 2026-09-25 a sibling document,
`NSC-078_DECISIONS.md`, was committed and reverted 41 minutes later because it read as a standing
list of decisions while a committed, hash-pinned artifact
(`Docs/Art/Environment/NSC-078_ART_PLAN.md` section 5) already carried a *more complete* version of
the same numbered list. A dated record that looks like current truth is the failure mode; naming
the date and the owning contract is the fix.

## What is here, and why it is here at all

Nine documents, 77,743 bytes as authored. Until this commit they existed in **no git repository** —
they sat only under `C:\nscrev\ger-contract-revisions-20260916\` on a single disk, while 14 task
contracts cited them 68 times. Those citations are all provenance: `.provenance.owner_decisions`,
`.provenance.contract_followups[].reason`, `.notes`, `.decomposition_reason`, `.execution_reason`,
and `.reference` fields on acceptance criteria, completion gates and GDD evidence.

**No acceptance criterion and no completion gate anywhere states a *requirement* that depends on
these files.** Nothing is blocked by their absence and nothing is released by their presence. This
commit is a backup and a convenience for readers, nothing more.

| file | records decisions for |
| --- | --- |
| `SPELL_DECISIONS.md` | NSC-007, NSC-008, NSC-009 — shared spell decisions S1–S7 |
| `REV4_DECISIONS.md` | NSC-007, NSC-008, NSC-009 revision 4 follow-ups |
| `RESTART_VICTORY_DECOY_DECISIONS.md` | NSC-033 rev 9, NSC-086 rev 3, NSC-030 rev 10 |
| `NSC-030_REV6_DECISIONS.md` | NSC-030 revisions 6, 7 and 8 (D21–D27) |
| `NSC-030_DECISIONS.md` | NSC-030 encounter design, items 13–20 |
| `NSC-033_NSC-049_DECISIONS.md` | NSC-033 rev 8, NSC-049 rev 6, NSC-017/NSC-053 wording |
| `NSC-055_REV4_DECISIONS.md` | NSC-055 revisions 4 and 5 (E1–E6, G1–G7) |
| `NSC-066_REV2_DECISIONS.md` | NSC-066 revision 2 (T1–T6) |
| `NSC-088_REV5_DECISIONS.md` | NSC-088 revision 5 (F1–F8) |

## What was measured before landing them

The test that caught `NSC-078_DECISIONS.md` was **supersession**: is this content already carried by
a committed, hash-pinned artifact? Measured against main `7c9c290e` on 2026-09-25, for all nine:

- **No committed artifact carries their decision statements.** Distinctive phrases from the decision
  text return zero committed files. The only non-zero hits are General Design Document language the
  documents quote, and `Tasks/NSC-055.yaml` restating one conclusion in its own words. A positive
  control — a phrase from the superseded NSC-078 document — does resolve, in the committed art plan,
  so the probe works.
- **Nothing hash-pins any of them.** Across the 14 citing contracts, the only fields where a sha256
  and a decision-document name share one value belong to NSC-078, the control.
- **Zero requirement citations**, as above. `NSC-078_DECISIONS.md` sat in four acceptance-criterion
  requirements and one gate requirement; these sit in none.

## One byte-level note

`SPELL_DECISIONS.md` was authored with CRLF line endings; the other eight use LF. This repository
sets `core.autocrlf=true` and `.gitattributes` does not exempt this path, so the committed blob of
that one file is 12,228 bytes against 12,316 on the host — 88 carriage returns normalized, content
identical. No hash gate pins these files, so nothing depends on the original bytes; the difference
is recorded here so a future reader does not read it as corruption.
