# NSC-015 death looks: art direction, then an estimate

Art Director Agent, 2026-09-17. For the GER Agent. **No generations spent; none proposed without Vincent's word.**

Vincent's request, verbatim: "**Corpse sprite that looks blasted, bloody, decapitated, burned, arm chopped off**",
then "**We want multiple death positions**" / "**or death looks I mean**".

Read as intent: **deaths should look properly violent, and varied** - not one tidy fade-out.

## 1. The style call

**Yes to properly violent and varied. No to literal anatomical gore** - for two independent reasons, and the
second one would apply even if the bible said nothing.

**Reason one, the identity.** The prompts that produced the approved enemies and the approved architecture kit
carry "no gore, family-friendly" as a literal clause, and the register is dark-but-cute horror-comedy. Literal
severed necks and blood spatter do not sit in the same frame as a grumpy wizard with a book on his belt. Changing
that is Vincent's to decide, not mine - but it is a **bible change**, not a prop request, and it would apply to
everything afterwards.

**Reason two, and this one is not negotiable by taste: at this size literal gore does not read.** A defeated body
occupies roughly 60 to 90 px on screen at 1080p. A neck stump is 3 to 5 px, a blood spatter 2 to 4 px per fleck.
Anatomical detail at that scale turns to mud - it reads as noise or dirt, not as violence. What reads at 60 to 90
px is **silhouette** and **one or two strong colour accents**. So the most violent-looking death at this scale is
also the most stylised one.

**What does deliver "properly violent" here:**

| Device | Why it reads |
|---|---|
| **Silhouette first** | the shape tells the story: flat and splayed, crumpled into a heap, curled and scorched, a body whose head-shape is missing |
| **Separate small pieces** | decapitation reads as a **head-shaped prop lying beside the body**, not as a wound. Same for "arm chopped off": a separate arm shape a few pixels away. Unmistakable at 4 px, and comic rather than clinical |
| **Palette accents, not spatter** | a small dark plum-red pool under the body, in the existing shadow palette, rather than bright red flecks. Burns as charcoal black with two or three ember-orange pixels and a smoke wisp |
| **Comic-grotesque punctuation** | X eyes, a tongue out, a skull motif, the lantern rolled away and gone out. This is the register the game already lives in, and it makes death funny-dark rather than grim |

That gets Vincent variety and impact, keeps the style he approved, and is the version that survives being 80 px
tall.

## 2. A correction the request needs: the wraith does not bleed

"Bloody, decapitated, arm chopped off" applies to the **Dungeon Brute**. The **Lantern Wraith** is a spectral
thing carrying a lantern - it has no arms to sever and no blood. Giving it the same four looks would read as a
bug, not as violence.

So the looks are **per enemy type**:

**Dungeon Brute (physical):**
1. **blasted** - flat on its back, limbs splayed, cleaver thrown clear;
2. **burned** - curled, charcoal silhouette, two or three ember pixels, one smoke wisp;
3. **decapitated** - body face-down, head-shaped prop lying beside it, small plum-red pool;
4. **dismembered** - one arm as a separate shape a few pixels away, cleaver still in its hand.

**Lantern Wraith (spectral):**
1. **dissipated** - cloak collapsing empty, wisp scattering upward;
2. **snuffed** - lantern fallen and dark, cloak puddled around it;
3. **shattered** - lantern broken, its flame-wisp bursting outward in pieces;
4. **unravelled** - the cloak's silhouette torn open, wisp draining out of the tear.

Both sets are violent and varied; neither asks the art to do something the creature is not.

## 3. The random-versus-matched fork

**Random variants, as you assumed** - with one cheap exception worth taking.

- Matching the look to the killing blow multiplies the art by damage type **and** needs a system that records the
  killing blow. That is its own expansion.
- With four looks per type, random already delivers the variety Vincent asked for.
- **The exception that costs no art:** if fire damage exists as a distinct type, gate the **burned** look to fire
  kills and pick randomly among the rest otherwise. One special case, zero extra sprites, and it buys the moment
  where the death matches what the player just did.

## 4. Estimate, in meter terms

Per the spend evidence, printed quotes run under the meter; budget at about 1.4x printed and count the task's own
call log against the cap.

- Each look is **one still sprite**, `create_object_pro_flash`, `n_directions: 1`. A body lying down wants roughly
  a 2 x 1 x 0.4 world-unit footprint, which is a 144 x 96 canvas - quoted at **6 printed**.
- **One screen orientation per look.** The camera is fixed; a corpse authored lying in one orientation reads
  correctly, and per-facing corpses would multiply the set by four or eight for no gain. This is the single
  biggest cost decision in the estimate.
- 4 looks x 2 enemy types = **8 sprites = 48 printed ≈ 67 metered**.
- Re-rolls, at the rate this run has measured (about 1 in 5 needing one): 2 or 3 more sprites, **12 to 18 printed
  ≈ 17 to 25 metered**.
- **Proposed cap: 90 generations**, stop and ask past it.

If Vincent wants a fifth look per type, add about 17 metered per type.

## 5. Two things the art needs from the contract

- **The ground line.** Death sprites must be aligned the way NSC-095 rev 4 aligns the wizards and NSC-077 aligns
  the enemies: every frame's lowest opaque row on one row per sprite set, so a corpse sits on the floor rather
  than floating. `plant_feet.py` already does it and costs nothing.
- **No collision is right, and it helps here.** Vincent's call that defeated bodies carry no collision means a
  corpse can extend past its nominal footprint - a thrown cleaver, a rolled head - without blocking a doorway.
  That is what makes the "separate small pieces" device affordable.

## Batch status, 2026-09-17 late (local)

**Vincent approved the direction and the batch** - relayed by the GER Agent from his own session: stylised-violent
rather than literal gore (he chose it with the scale arithmetic in front of him), **cap 90 generations**, 8
sprites, one screen orientation per look, stop and ask past 90.

**Then he called quiet mode** - "We need to focus on the video and kind of quiet everything" and "I dont want to
answer questions on anything else right now, we need fireballs" - so **the batch is HELD after one sprite.**

| # | id | canvas | seed | printed | object | outcome |
|---|---|---|---|---|---|---|
| 1 | `death_brute_blasted` | 144x96 | 40001 | 6 | `4423f1d2-08ee-44d8-ba0a-c81abeeb95f0` | generated before quiet mode; parked in `samples/` |

**6 printed of the 90 cap.** The remaining seven are not started: brute burned, decapitated, dismembered; wraith
dissipated, snuffed, shattered, unravelled. The prompts are in section 2 above and the canvas is settled at
144x96 (footprint 2 x 1 x 0.4 units: width (2+1) x 0.7071 x 64 = 136, height (0.4 x 0.866 + 3 x 0.3536) x 64 =
90, so 144x96 with margin).

**One clause deviation the batch needs, and the GER Agent has already accepted it:** the committed prop clause
ends "no other objects", but the separate-pieces device *is* another object in the same sprite - a thrown cleaver,
a rolled head. The prompts say "no other objects except the body and the pieces described". The first sprite
confirms it works: the cleaver landed clear of the body, as asked.

**Contract split to remember:** the Brute's four looks are NSC-015 AC-006, the Wraith's four belong to the wraith
task. One art run, two contracts consuming it.

## Round 1 results, all eight, and the four that failed the brief

Generated 2026-09-18 (local 09-17 late), 144x96, `create_object_pro_flash`, `n_directions 1`, 6 printed each.
Sheet: `death_looks_2x.png`. Measurements: `measurements.json`.

| # | id | seed | object | verdict |
|---|---|---|---|---|
| 1 | `death_brute_blasted` | 40001 | `4423f1d2-08ee-44d8-ba0a-c81abeeb95f0` | **keep** - on its back, limbs splayed, cleaver thrown clear, exactly the brief |
| 2 | `death_brute_burned` | 40002 | `a102f7b2-29c4-4747-8d08-687a2e71bce0` | **keep, weakest silhouette** - charred heap with embers and one smoke wisp; the shape is mushy but reads as burned |
| 3 | `death_brute_decapitated` | 40003 | `693166c8-0c4e-471f-84a1-bd7faf8a13e1` | **re-roll** - the fallen hood is right, but a bright red wound rosette sits at the neck. That is the literal anatomical read Vincent's approved direction rules out |
| 4 | `death_brute_dismembered` | 40004 | `1a791813-e690-4431-a7b8-49959eeee6ea` | **re-roll** - separate arm with the cleaver is right; the blood came back **magenta**, not the plum shadow the brief asks for, and the body silhouette is muddled |
| 5 | `death_wraith_dissipated` | 40005 | `56059dfa-96a2-4529-8606-14004efd373d` | **keep, best of the set** - empty cloak collapsing, teal wisp scattering upward out of the collar |
| 6 | `death_wraith_snuffed` | 40006 | `e8c7d38f-3a15-4386-b5cb-23ef8a835577` | **re-roll** - the cloak is **standing upright and hooded**, so it reads as a live wraith beside a dead lantern. Palette also drifted pink |
| 7 | `death_wraith_shattered` | 40007 | `6da672cb-9ad2-427a-9473-60f124c686d2` | **keep** - lantern burst open, teal flame in separate shards, cloak flung flat |
| 8 | `death_wraith_unravelled` | 40008 | `89f40548-a7dc-48c6-aba9-520158027751` | **re-roll** - the teal drain is good but the cloak is again **upright**, so it does not read as defeated |

**The pattern in the two wraith failures is worth naming:** "puddled in a heap" and "lying slumped" were not enough
to stop the model drawing a standing cloak - a hooded cloak is overwhelmingly drawn upright. The re-roll prompts
say it four ways: "lying completely flat", "spread out like dropped laundry", "the hood lies flat and empty on the
floor", "nothing is standing, nothing is upright, there is no figure and no body wearing it". The same fix that
worked on the NSC-078 masonry, where "no intact arch" had to be pinned alongside the palette.

**And in the two brute failures:** asking for "a small dark plum-red pool" invites red. The re-rolls remove the
noun entirely - "just dark shadow, no wound, no blood, no red, no pink, no magenta, no spatter, nothing
anatomical" - which is the same lesson as writing rules about relationships rather than things: name what the
thing must not promise, not the fluid it may contain.

| # | re-roll | seed | object |
|---|---|---|---|
| 9 | `death_brute_decapitated_r2` | 40013 | `083e969b-85ca-4491-aa4a-e13000fd57d9` |
| 10 | `death_brute_dismembered_r2` | 40014 | `5831dfc8-15f6-4a6b-b169-3332bc88aa0b` |
| 11 | `death_wraith_snuffed_r2` | 40015 | `c6af695d-437a-4ee7-848f-55ad79a30c30` |
| 12 | `death_wraith_unravelled_r2` | 40016 | `168245b2-4730-46a8-b056-b699ea1cdf51` |

**Printed: 12 calls x 6 = 72 of the 90 cap.** One re-roll each and no more - a second round would reach 96 and
breach it, so if a re-roll still fails, both versions go to Vincent and the decision is his.

**Ground line, measured before any alignment:** lowest opaque row runs 87 to 94 across the eight, a **7 px
spread**. The contract's alignment requirement handles this with `plant_feet.py` at zero generations: every
sprite's lowest opaque row onto one row, then `pivot y = (96 - (row + 1)) / 96`.

## Round 2, the recommended eight, and the spend

**All four re-rolls delivered.** Sheets: `death_rerolls_compare.png` (round 1 against round 2 as generated),
`brute_pairs_locked_3x.png` (the two brute looks after the colour lock, at 3x), `death_final_2x.png` (the
recommended eight), `death_gamescale_1080p.png` (1:1 at 1080p beside the wizard).

| Look | Recommended | Why |
|---|---|---|
| brute blasted | **round 1** | on its back, limbs splayed, cleaver thrown clear. The clearest of the four brutes |
| brute burned | **round 1** | charred heap, embers, one smoke wisp. Mushy silhouette, but unmistakably burned |
| brute decapitated | **round 2** | round 1 kept a wound spiral at the neck even after the colour lock, and a wound is the one read Vincent's approved direction rules out. Round 2 is just a dark hollow plus the hood lying beside it. It costs legibility - the body reads as a bundle - and that is the right trade |
| brute dismembered | **round 1** | **reversed after measuring.** Round 2 lost the severed arm entirely, so it read as a dropped weapon and looked nearly identical to decapitated round 2. Round 1 has the separate arm still gripping the cleaver, and the shared 48-colour lock pulled its blood from salmon `(251,145,96)` to plum `(137,73,104)` - inside the approved palette without another generation |
| wraith dissipated | **round 1** | best sprite in the batch: empty cloak collapsing, teal wisp scattering out of the collar |
| wraith snuffed | **round 2** | round 1's cloak stood upright and hooded, reading as a live wraith beside a dead lantern. Round 2 is collapsed and the pink drift is gone |
| wraith shattered | **round 1** | lantern burst open, teal flame in separate shards, cloak flung flat |
| wraith unravelled | **round 2** | round 1 stood upright too. Round 2 lies flat with the teal draining low across the ground |

So round 2 wins three and round 1 wins one of the four re-rolls - and the one reversal came from looking at the
locked files rather than trusting the re-roll to be better because it was newer.

### Colour lock and alignment, both verified

- **One shared 48-colour palette across all twelve sprites**, quantized together in a single `reduce_colors` call:
  the union of colours across the twelve is exactly 48.
- **Ground line: every sprite's lowest opaque row moved onto row 92 of 96, spread 0**, by whole-pixel shifts only
  (`tools/align_ground.py`, shifts -2 to +9). Opaque pixel counts unchanged, nothing clipped, report in
  `aligned/ground_line_report.json`. **Pivot for the whole set: `(0.5, 0.03125)`** = (96 - 93) / 96, the same
  formula the enemy metas use.

### Spend: the subtraction, both reading pairs quoted

| When | Remaining | Used |
|---|---|---|
| Before the first death call, queue empty | **4381** | **618** |
| After the last, queue empty | **4309** | **690** |

**690 - 618 = 72, and 4381 - 4309 = 72.** Both columns agree. **72 of the 90 cap**, from 12 stills at 6 printed
plus one `reduce_colors` at 0.1 - printed and meter agreeing again, as the fireball run did.

**18 generations of headroom left and no further spend planned.** A second re-roll round would have reached 96
and breached the cap, which is why both versions of the contested looks went to Vincent instead.

### What the two failure patterns taught, worth carrying to the next batch

1. **A hooded cloak is drawn upright unless you forbid it four ways.** "Puddled in a heap" and "lying slumped"
   both produced a standing wraith. What worked: "lying completely flat", "spread out like dropped laundry", "the
   hood lies flat and empty on the floor", "nothing is standing, nothing is upright, there is no figure and no
   body wearing it".
2. **Naming the fluid invites the fluid.** "A small dark plum-red pool" produced salmon and magenta blood. The
   re-rolls removed the noun - "just dark shadow, no wound, no blood, no red, no pink, no magenta, no spatter,
   nothing anatomical" - which is the same shape as writing rules about relationships rather than things.
3. **And the cheap fix that nearly went unnoticed:** a shared palette lock can pull an off-palette colour back
   inside the family, so re-check the *locked* file before condemning a composition. That is what saved
   dismembered round 1 and its separate arm.

## Vincent's three decisions, 2026-09-18, and what they change

1. **"All four contested brutes ship."** Both rounds of decapitated and both of dismembered become looks in their
   own right, so the Brute has six.
2. **"So we want all of the art :)"** - so the two wraith sprites I had rejected ship too. **Nothing is
   rejected; the rejects branch gets nothing from this batch.** Their cloaks stand upright, which is why I
   rejected them, and that turns out to be defensible for a *spectral* enemy: the cloak **is** the creature, so it
   can die standing. Renamed for what they show rather than the round they came from:
   - **hollowed** - standing but empty and slack, lantern fallen dark at its feet (was snuffed round 1);
   - **draining** - caught upright mid-dissolve, teal spirit pouring from the collar (was unravelled round 1).
   **One caveat for whoever writes the AC:** at gameplay scale an upright cloak can read as a live wraith for a
   beat, so these two are better as the rarer variants than as the default.
3. **Selection is not random any more.** His words: *"so example.. you get killed with 1 shot, then you are
   decapitated"* and *"if you need multiple shots to kill you, you lose an arm"*. That is **hit-count driven**,
   and it needs only "was this a one-shot kill" on the killing blow - not a damage-type system.

### The mapping I proposed to the GER Agent, gaps named

| Trigger | Brute | Wraith |
|---|---|---|
| one-shot kill | **decapitated** (a or b at random) | **shattered** - the lantern bursts open |
| more than one hit | **dismembered** (a or b at random) | **unravelled** or **draining** - the cloak gives way |
| fire kill, if fire is a distinct damage type | **burned** | - |
| no rule matches (default) | **blasted** - the flat-on-its-back knockback pose, which also suits a heavy or full-charge killing blow | **dissipated**, with **snuffed** and **hollowed** as rarer variants |

**Two variants per rule-driven look is the point of shipping all four** - once the rule picks the look, a random
choice between its variants stops the same rule producing an identical corpse every time.

**Vincent gave the GER Agent these rules directly as well, and asked me to confirm with them** - sent 2026-09-18,
including the three gaps above and the request to reconcile if their version of his wording differs from mine.

### Delivery

`staged/Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source/Death` - twelve PNGs plus
`staged/death-inventory.json` (ids, seeds, silhouette notes, canvas, alpha bbox, ground row, pivot, sha256,
colours, the selection rule and the spend readings). Sheet: `death_all_twelve_2x.png`.

- **144x96, 64 PPU, point filter**, one shared 48-colour palette (union across the set exactly 48);
- **every sprite's lowest opaque row on row 92 of 96, spread 0**, so **one pivot serves all twelve:
  `(0.5, 0.03125)`**;
- **the sha256 values are of these bytes** - copy them verbatim, a re-export changes every hash;
- **spend unchanged at 72 of the 90 cap** (4381/618 before, 4309/690 after). Shipping the two former rejects cost
  nothing: the art already existed.

### One style consequence, recorded so nobody "fixes" it later

**`decapitated_a` keeps a small wound spiral at the collar.** Vincent chose it with the sprite in front of him, so
a wound read is now inside the approved family. It should not be removed later by citing the
stylised-not-literal-gore direction - that direction is still right for *new* art, and this sprite is an
explicit exception he made.

## Reconciled with the GER Agent, and the two defects I sent back

The GER Agent adopted my reading of Vincent's rule over its own - it had heard "pick the other" and read it as
*the other variant of the same look*, a mild-versus-severe pair, which would have wired r1/r2 as severity when
those variants differ in **legibility**, not severity. Its first reconciled table still had two defects:

1. **Four of the twelve sprites were unreachable.** Every kill has either one damaging hit or more than one, so a
   "no rule matches" branch never fires and "rare -> hollowed" had no trigger at all. That hid `blasted` for the
   Brute and `dissipated`, `snuffed` and `hollowed` for the Wraith - a third of the art Vincent had just asked to
   use in full.
2. **Precedence was undefined.** A one-shot fire kill matched both the hit-count rule and the fire rule.

**The corrected mapping I sent, first match wins:**

| Order | Condition | Brute | Wraith |
|---|---|---|---|
| 1 | fire kill, where a distinct fire damage type exists | **burned** | - |
| 2 | one damaging hit **and** it was a heavy or charged blow | **blasted** | - |
| 3 | one damaging hit | **decapitated** (a or b at random) | **shattered**, or **dissipated** as the rarer variant |
| 4 | more than one damaging hit | **dismembered** (a or b at random) | **unravelled** or **snuffed**, with **draining** and **hollowed** as the rarer variants |

**Why those assignments come from the sprites rather than from taste:** `shattered` is the lantern bursting open,
which is sudden, so it belongs to the one-shot. `snuffed` and `unravelled` are quiet and progressive, which is
what being worn down looks like. `draining` and `hollowed` are the two upright cloaks, so they stay rare. And
`blasted` is flat on its back with the cleaver thrown clear - a knockback pose - which is why a heavy or
full-charge killing blow is its natural trigger instead of a default that never fires. NSC-098's charge tiers
supply that signal already.

**One wording question left with the GER Agent:** whether "one damaging hit" counts the enemy's whole lifetime
(so a chip and then a kill is a two-hit death - my reading) and whether a damage-over-time tick counts as a hit.
If burn ticks count, a burning enemy can almost never die a one-shot death and `decapitated` quietly becomes rare.

## The heavy-blow trigger: threshold accepted, units corrected

The GER Agent replaced my "read NSC-098's charge tier" with **the killing blow's damage meeting a serialized
threshold**, since `EnemyHealth.TakeDamage(float)` already carries the magnitude and NSC-098 is nowhere near
delivering. **Better than my version, and not only cheaper:** "heavy or charged blow" was me naming the one heavy
source I knew about, while magnitude is its general form - a crit, a future heavy weapon or a trap all trigger
`blasted` with nobody wiring them in.

**What I sent back: express the threshold relative to the enemy's max health, not as an absolute float.**

1. **An absolute number goes stale silently.** Rebalance damage and nothing fails - the death looks just quietly
   change. Relative survives every balance pass and one threshold covers enemy types with different health pools.
   This is the same lesson as [[write-rules-about-relationships-not-things]] applied to a number.
2. **`blasted` and `decapitated` compete for the same bucket.** Vincent's own words name decapitated as *the*
   one-shot death. A threshold set low relative to real enemy health means almost every one-shot kill clears it,
   so blasted becomes the normal one-shot death and decapitated turns rare - **inverting his rule while
   satisfying every gate.** So the threshold belongs with the rarity weights under VAL-004, where he tunes what he
   sees.
3. **VAL-003 needs extending for the same reason.** Reachability now depends on the serialized threshold, so the
   gate must assert that **both** `blasted` and `decapitated` are selectable at the shipped default: a threshold
   above any achievable damage makes blasted unreachable again, and a threshold of zero makes decapitated
   unreachable. Checking the look list alone passes both cases.

Accepted from the GER Agent without change: hit counting over the enemy's current life with a reset on
`ResetHealth()`, damage-over-time ticks **not** counting as hits (otherwise a burning enemy could almost never die
a one-shot death), VAL-003 as a hard gate, VAL-004 leaving rarity to Vincent, and the wound-spiral note entering
the contract as a prohibition rather than an observation.

## A fourth defect, and this one was mine

Giving `blasted` a real trigger fixed its unreachability and **opened a hole at the other end**. The GER Agent's
original table had "no rule matches -> blasted", which never fired for hit counts of one or more - the defect I
reported - but it did cover the case my fix removed: **a death with zero damaging hits.**

That happens on any kill that does not route through `TakeDamage`: a crushing door or hazard, a scripted kill, a
despawn-as-death, an out-of-bounds cleanup, or a test calling `Kill()` directly. Hit count 0 matches neither "one
damaging hit" nor "more than one", so with blasted moved to the heavy-blow branch, a zero-hit death selects
nothing at all.

**The restored catch-all, as the last line of the order:**

| 5 | zero damaging hits, or the count is unknown | **blasted** | **dissipated** |

`blasted` carries it for the Brute because the pose is source-agnostic - flat on its back reads for a hazard as
well as for a heavy blow - and `dissipated` is the Wraith's most neutral death. Both are already reachable
through their own rules, so this adds nothing to VAL-003's reachability burden; it only guarantees the selector
always returns something.

**And one more clause sent with it:** nothing in the mapping said the chosen look is **fixed at the moment of
death**. If selection runs on enable, per frame, or again when a pooled corpse is re-shown, the same corpse can
change sprite while the player watches - and a random variant makes that visible. The look and its variant are
chosen once when the enemy dies and cached on the corpse.

**The lesson, and it is about my own fix rather than anyone else's:** removing an unreachable default is not free.
A branch that never fires for the cases you are thinking about may be the only branch covering a case you are
not. When you delete a catch-all, enumerate what was falling into it first.

## Fifth pass: one defect, one scope question for Vincent, one unstated decision

**Defect - corpses must sort by their pivot, never by sprite bounds.** This one comes straight out of the art
direction: the separate-pieces device puts a thrown cleaver, a severed arm or a fallen hood several pixels clear
of the body, which is affordable only because Vincent ruled that defeated bodies carry no collision. The result
is a sprite **2.25 world units wide** whose body occupies far less. If the isometric sort uses renderer bounds
instead of the pivot's ground point, a corpse flickers in front of a wall, a door or a live enemy beside it - and
the wider the separate piece, the worse it looks. **These sprites break the usual assumption that a sprite's
bounds approximate its footprint,** so it needs stating rather than assuming.

**Scope ambiguity - whose death is the rule about?** Vincent said *"you get killed with 1 shot, then you are
decapitated"* and *"if you need multiple shots to kill you, you lose an arm"*. I have read **"you" as generic**,
meaning whatever gets killed, and every sprite in this batch is an **enemy** corpse - six Brute, six Wraith. If he
meant it literally, about the player, then **the wizard has no death art at all, not one frame**, and the
contracted rule would silently only ever apply to enemies. Raised with the GER Agent and asked of Vincent
directly, because it is his sentence to interpret. If he does want player death looks: roughly four looks at
128x128, about 24 printed, and it needs his own go and a cap.

**Unstated decision - how long does a corpse persist?** Nothing anywhere says. If corpses stay for the level, a
busy room accumulates 2.25-unit-wide bodies with pieces scattered across the floor, which is a different look
from a room that clears. **No new art either way** - a fade is a tint over time - but "corpses persist forever" is
a decision if nobody makes it.

## Vincent's two answers - ALREADY ASKED AND ANSWERED, do not re-ask him

Both went to him through the GER Agent on 2026-09-18, with the consequences spelled out:

1. **"Enemies (what we built)"** - the death rule is about enemies, not the player. My generic reading of "you"
   was right, all twelve sprites are correctly scoped, and **the wizard still has no death art of any kind.** If
   player death looks are ever wanted that is a new batch: roughly four looks at 128x128, about 24 printed, and it
   needs his own go and a cap.
2. **Corpses stay for the level. No fade.** He took it with the clutter consequence stated: 2.25-unit-wide
   sprites, pieces scattered, accumulating in a busy room, no collision so they never block a doorway.

**And the defect from the fifth pass is accepted:** corpses sort by their **pivot ground point**, like a
character, never by sprite extent, with the NSC-039 sorting band and the isometric transparency sort axis named in
the clause so nobody re-derives it.

### What persistence makes newly relevant (sent to the GER Agent, not a defect)

Because corpses never clear, overlap is permanent rather than momentary. Two mitigations, both free of art:

- **The selector avoids repeating the look chosen for the immediately previous corpse of the same enemy type.**
  With six looks that costs nothing in variety and it stops two identical bodies sitting side by side - the
  arrangement that reads as a bug rather than as carnage.
- **A small random positional offset, well inside the corpse's own footprint.** Identical pieces landing
  pixel-aligned on top of each other is what makes a pile look like a rendering fault; a few pixels of jitter
  makes the same pile read as intentional.

Shipping **six** looks per enemy rather than four is what makes persistence survivable, which is a retrospective
argument for Vincent's "we want all of the art".

## My mitigation was wrong, and the corrected form

The GER Agent caught it: **"avoid repeating the look chosen for the previous corpse" would have overridden
Vincent's own rule.** Two brutes each killed by one shot must *both* be decapitated - that is what he said - and a
look-level no-repeat would have forced the second to something else. It would also have passed every gate: each
look stays reachable, the mapping still "works", and the only symptom is his rule intermittently not applying.
**That is the same failure shape I had been reporting in its text all evening, one level down in mine.**

**Corrected form, adopted:** never repeat the same **variant** of the same look back-to-back for that enemy type,
and never let that adjust the look itself. Two one-shot kills give decapitated twice - correct - as `_a` then
`_b`. Where a look has no second variant (`blasted`, `burned`, `shattered`), a repeat is simply allowed, because
overriding a kill-type rule to avoid a cosmetic repeat is the mistake again.

**Two precisions I sent back on the corrected version:**

1. **The jitter is a world-space offset on the ground plane, never a sprite-space or screen-space one.** Both
   satisfy "inside the footprint" and "alignment still holds", but only one is correct. Offsetting the corpse's
   world position along the floor keeps the pivot on the floor, keeps pivot-based sorting consistent, and
   legitimately moves it up the screen as it moves back. Nudging the **sprite's** local position in pixels looks
   identical in a still frame and **undoes the alignment pass** - the corpse floats by exactly the jitter amount,
   the one defect the whole set was aligned to one row to prevent. Whoever implements it will reach for the sprite
   transform first, because it is the nearer handle.
2. **With exactly two variants, "never repeat back-to-back" is strict alternation, not randomness** - `a-b-a-b`
   for as long as that look keeps being selected. Visually fine, and not worth adding probability to avoid, but
   it should be named as intended in the criterion so "the variants are not random" dies as a bug report before
   it costs a run.

All four items fold into **NSC-015 revision 14** (corpse sorting by pivot, persistence for the level, variant
no-repeat, positional jitter), held until the NSC-007 decomposition releases main. **NSC-099 needs nothing
further - every one of these is defeat-response behaviour rather than sprite identity, so the art side is
closed.**
