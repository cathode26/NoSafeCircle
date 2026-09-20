# Demo video: what is wrong, what the three tasks fix, and the order to shoot it

For Vincent, 2026-09-17. His plan: *"I need a script on what is wrong. I need to talk about and show what the 3 tasks will fix. Then we need the game agent to run the 3 tasks. We record the fixes happening on the viewer. We then merge all of the projects into main and I open main and test the fixes. We need to get the art for the fireball first."*

## Read this first: only one of the three is a fix

The plan says "show what the 3 tasks will fix". Two of them are not fixes, and the video will not survive contact with the footage if we claim otherwise.

| Task | What it actually is | What you can truthfully say on camera |
|---|---|---|
| **NSC-007 Charged Fireball** | **A real fix**, but only for walls. The code does not exist yet; a crew builds it | "The fireball goes through walls. This task makes solid geometry stop it." **Doors need the seam fix too** - see section 2 |
| **NSC-091 Enemy detection and search** | **Already on main.** Both claimed files exist; it needs a PlayMode run and a record, not a crew | "Here is the enemy noticing me, chasing, and searching where it last saw me." A feature demo, not a fix |
| **NSC-044 Ruined Entry blockout** | **Already on main.** All seven claimed files exist; needs an EditMode run and a record | "Here is the first real room instead of a prototype box." A feature demo, not a fix |

**The honest framing that still tells a good story:** two features are finished and undocumented, one feature is missing, and the video shows all three plus the machinery that produces them. That is a truer and more interesting story than three bugs being fixed, because it is what the project actually looks like.

## The bugs, and who owns each

### 1. The fireball shoots through walls and doors — **NSC-007 fixes it**

**Cause, verified in the code:** the fireball you can cast today is not a real component. It is embedded in `DemoRunFlow` (`TryFireAtCursor`), and it performs **no line-of-sight check at all** — nothing stops it.

**What NSC-007 does:** deletes that embedded fireball, creates `Fireball.cs` and `FireballProjectile.cs`, and its acceptance criteria require that *"solid gameplay colliders block Fireball's projectile: walls, obstacle and prop colliders (shelves, pews, columns, rubble), and any door whose doorway-blocker collider is enabled ... only an open door the wizard has not yet crossed does not block"*, tested every tick with a chest-height raycast.

**So this bug is already designed out** — it was never an oversight, just unbuilt work.

### 2. The gap between the wall and the door — **needs its own task, and it affects NSC-007**

**Vincent spotted it from play:** *"The projectile went between the wall and the door, which means the enemy can see you when you walk past the door, it also means it can shoot through the gap in the door."*

**The Game Agent then measured it in Unity, at main `b7e46c320`, using the same query the enemy's sight check uses.** It is worse than the screenshot shows — the slot is on **both** sides of **every** door:

```
blocker enabled : True  (forced enabled by the probe, so this is not a door-state artefact)
blocker x span  : 2 units, centred      wall collision begins at +/-1.5
x offset -1.0 .. +1.0  -> hits DoorVisual
x offset -1.25         -> NOTHING, sightline OPEN
x offset +1.25         -> NOTHING, sightline OPEN
x offset +/-1.5 and out -> hits the wall
```

**Ten open slots across five doors.** The blocker is 2 units wide in a 3-unit opening, so a half-unit slit runs down each jamb.

**The cause is one line, and it says so out loud.** `DoorPrototypeSceneBuilder.cs:1088` sets `size = (2, 2.5, 0.3)` under a comment reading *"sized to the door's footprint"*. **The collision was sized to the door art instead of to the hole in the wall.** That is the whole bug.

**NSC-007 must not be credited with fixing this.** Its projectile raycast will find the same genuinely clear path, so NSC-007 can pass every acceptance test and the fireball will still fly through doors.

**Filming consequence, decide before shooting step 3:** either shoot NSC-007's "after" footage on a build that **includes the door fix**, or say plainly in the video that doors are a separate known defect. Otherwise the video shows a "fixed" fireball going through a door, and that falls apart the moment anyone tests it.

**The regression test the fix needs, and why the bug survived:** a single centre-line ray correctly hits `DoorVisual` and passes. Only a sweep across lateral offsets **and** heights, from **both** sides, with the blocker enabled, catches this. `DoorCrackProbe.cs` in `C:\nscrev\reports\door-crack-probe\` already does the lateral sweep and is the starting point.

**Ownership and scope:** the blocker geometry belongs to `NSC-020`, in `needs_replan`, so the GER Agent is drafting a **narrow** task: the blocker spans the painted jamb, with a sweep test over blocked-vs-open, both sides, several heights and offsets. **Deliberately not per art state** - `DoorInteractable` has no state enum, just three booleans and one toggled BoxCollider, so the seven art states map onto two collision shapes. State-dependent collision (and whether the broken door's painted hole should be a sightline) is a separate item alongside NSC-052. Contracting it here would produce a gate nothing could pass.

**Settled by Vincent, for the record:** *"A broken door occurs later, dont use it now. YEs an enemy can come through a broken door, they broke it."* So the broken state is out of scope for now, and when it is built the painted hole is a genuine opening - collision follows the art rather than sealing it. The same principle as the jamb seam, corrected in the opposite direction.

**On camera:** this is the strongest segment in the video. The bug is visible in one still, the cause is one line of code with a comment that explains the mistake, and the fix is measurable.

### 3. Enemies grow 38% the moment they walk — **free to fix, and it will show on camera**

Found by the Game Agent while checking something else, measured in the scene rather than inferred:

```
walk frames  96 PNGs at 176x176,  imported at PPU 64  ->  2.75 world units
idle frames  16 PNGs at 128x128,  imported at PPU 64  ->  2.00 world units
```

Both sets sit in the same animator controllers, so **every enemy pops 38% larger the instant it starts moving and shrinks when it stops.** It has been in the game as long as the art has; it reads as liveliness until you know, and then you cannot unsee it.

**The fix costs nothing:** set the walk frames to `spritePixelsToUnits: 88`, because `176 / 88 = 2.00` exactly. A meta change across 96 files, no regeneration, no PixelLab spend. Re-exporting the walks at 128 px would also work and would throw away resolution the art already has.

**It also settles the scale question** that was heading for a design debate: the **idles already match the 128 px / 64 PPU standard** used by the doors and the NSC-095 wizard art. The enemy art is not an outlier — only its walk frames are, and by import setting rather than by design. Nothing to choose; something to correct.

**Correction to an earlier claim of mine, recorded here because it reached Vincent:** I reported the enemy art as unwired. It is not. All 112 PNGs are cited by animation clips, every clip sits in a controller, and both controllers are attached to the authored enemies — verified by a scene probe. My sweep had grepped `.cs`, `.unity`, `.asset` and `.prefab` while omitting `.anim`, and Unity references by GUID rather than filename. **The door art genuinely is unwired; the enemy art never was.**

### 4. What the viewer footage actually shows

The viewer shows tasks moving through the pipeline — reserved, working, candidate, integrated. It does **not** show a fix happening in the game. So it is b-roll for the middle of the video: the machine doing the work, cut against before/after gameplay.

## Shooting order

**1. Fireball art first, as you said.** Cap approved at 100 generations. Blocked on one thing: the GER Agent is deciding whether the fireball VFX rides NSC-007 or needs its own task, because NSC-007's scope stops at a "placeholder-feedback boundary". Until that is settled the Art Director has no contract to work against.

**2. Shoot the "before" footage now, on today's main.** This is the only footage that expires — once NSC-007 lands you cannot re-shoot the fireball going through a wall without checking out an old commit.
- fireball fired through a wall and through a closed door;
- the enemy reacting to you through the closed door, and the projectile crossing the wall/door seam - the shot you already have;
- the current prototype room, for contrast with NSC-044's Ruined Entry.

**3. Evidence passes — NSC-089 and NSC-091.** One EditMode run, one PlayMode run, no crew, no spend, none of your time. These also unblock about 17 downstream tasks, which is worth saying on camera: the work was done, the paperwork was not.

**4. The NSC-007 crew run**, with the viewer recording. Expect roughly 30-40 minutes; the previous attempt ran 36 minutes before a role timeout. One crew at a time while Unity is also in use.

**5. NSC-044's gate needs you personally**, as do NSC-045 and NSC-048 — batch them into one sitting with the wizard chain's five rather than five separate interruptions.

**6. Integrate, then your test on main.** Merges are yours to authorise, one at a time, and nothing is pushed to GitHub without your word for that push.

## Suggested narration beats

1. **Cold open — the bug reel.** Fireball through a wall. Enemy watching you through a closed door. Ten seconds, no commentary.
2. **"Here is why."** The fireball is a demo stub with no collision test at all. The doorway has a seam the blocker never covered. Both are known, both have owners.
3. **"Here is the machine."** Viewer footage: NSC-007 reserved, a crew working, a candidate appearing. This is the part nobody else's devlog has.
4. **"Here is what was already finished but unrecorded."** NSC-091's enemy tracking you and searching your last position. NSC-044's Ruined Entry. Say plainly that the constraint is evidence, not code — 102 of 119 blocking links point at work that is done but unrecorded.
5. **"Here is the fix."** Fireball with its new art, stopped by a wall, stopped by a closed door, passing an open one. **The closed-door shot needs the seam fix landed as well as NSC-007** - otherwise it will still go through, and the shot fails.
6. **Close on the doorway seam** as the next thing to fix - named, diagnosed, and with the regression test that will stop it coming back.

## What I still need from you

- **Nothing to start the before-footage** — that can be shot now.
- **The GER Agent's answer on the fireball art owner** gates the art, and the art gates step 5. I have asked and will chase it.
- **Your gate sitting** for NSC-044/045/048 plus the wizard chain, whenever suits.
