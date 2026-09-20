# Expanded wing and Spectral Decoy: GER results and recommended direction (2026-09-17)

GER Orchestrator (Claude). Both cycles ran four rounds on local main 32c6223d3. Packets:
- C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER\20260917-003348-NSC-088
- C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER\20260917-003348-NSC-085

## 1. Spectral Decoy (NSC-088): decided and committed

You delegated the spell design, so it is committed as revision 4 (`688bd05d0`). A Codex contract check is running. Next it goes to the Decomposition Agent for two ordered children: enemy target redirect first, then the spell itself.

**The spell**
- **Cast.** Press F. A translucent teal-violet phantom of the wizard runs along a real NavMesh path to the cursor point, then holds there.
  - Sealed and locked doors block its route; open and broken doorways don't.
- **Who follows it.** Every enemy currently pursuing the wizard switches to the phantom.
  - Melee enemies chase it.
  - Lantern Wraiths approach it and shoot at it.
  - Wisps pass through the phantom, so standing right behind it is still dangerous.
- **Cost.** 30 mana, a 4-second life, and a 24-second cooldown (starting values). Cooldown is the main limit.
- **When it ends.**
  - Enemies still near the wizard (inside their lose-target distance) resume pursuit.
  - Enemies farther away search the spot where the wizard was when they switched.
  - Nothing forgets the wizard, and the pursuit leash still applies.
- **Door play.** One decoy can buy a full five-second door attempt thanks to enemy travel time. You choose between spending it mid-room or saving it for a door.

**My read: good.** It does what you described: send a phantom down another corridor, hide behind cover and slip past. It works against both melee and Lantern Wraiths without making rooms safe, because of the 24-second cooldown, the shots that pass through, and the searches at the saved spot.
- If it proves too strong in play, we can add enemies (your balance lever) or lengthen the cooldown; the contract's tuning range is 18-35 seconds.
- Your VAL-006 play review judges readability at gameplay-camera scale.

## 2. Expanded wing (NSC-085): needs your approval

The planning contract is committed as revision 3 (`42dccd0d1`). It only writes the plan document. Nothing becomes canon until you approve.

**The proposal: "The Drowned Bell and Rootwell Circuit"**
- **Where.** An optional challenge detour entered from Lower Vault's east wall, after D3 and before D4. It returns to Lower Vault before D4, and D5 is unchanged.
- **Layout.** 8 rooms and 11 corridors:
  - Crooked Gatehouse → Drowned Bell Cistern (hub, a bell hanging over water).
  - Masonry branch: Keeper's Refectory → Choir Landing.
  - Natural-cavern branch: Glowmoss Breach.
  - Both branches meet at Rootwell Junction.
  - Two parallel routes (Dry Rib Walk, Low Sump Crossing) lead to Ossuary Confluence, with a Moth-Keeper Nook alcove.
  - Destination: the Lantern Sepulcher (violet and amber, a cage over corruption), then back to Lower Vault.
- **Gates.** Four sealed gates reuse the five-second door and its close-and-lock health restore; every other connection is an open archway.
- **Enemies.** 28 across seven encounters (3-6 each), under the 15 active cap. The playtest target is at most 3 survivors following you back to D4.
- **Elevation.** Visual only: stairs, ledges and sump routes on the flat gameplay plane, with no new movement mechanic.
- **Third enemy.** One reserved spawn slot in the Lantern Sepulcher, pending that enemy's own contract.

**Your seven decisions (my recommendation in brackets)**
1. **Connection.** Two gates on Lower Vault's east wall, at (20,57) and (20,72). [Approve]
2. **Purpose.** Optional challenge detour or mandatory. [Optional; see the idea below]
3. **Gates.** Four gated doors, archways elsewhere. [Approve]
4. **Elevation.** Visual only. [Approve]
5. **Scope.** All 8 rooms and 11 corridors, built in two phases: core and cavern first, then masonry. [Approve]
6. **Third enemy.** Reserve one Lantern Sepulcher slot. [Approve]
7. **Task graph.** A new content parent for the wing's build tasks. [Approve]

**Idea (needs its own GDD approval): a real reason to take the detour.** The GDD excludes loot and persistent progression, so today the only reward is the health restore at each gate. One awesome fit: the wizard learns the Spectral Decoy at the Lantern Sepulcher. The dangerous detour then pays off with the escape tool for the Final Room. The downside is that players who skip the wing never get the decoy. If you like it, I'll write the GDD request and revise NSC-088 to match. If not, the decoy stays available from the start.

## 3. One enemy question: do Lantern Wraiths attack locked doors?

NSC-017 left this for you, and NSC-055 (the Lantern Wraith gameplay prefab) is waiting on it. I'm writing NSC-055 revision 4 so it doesn't assume an answer.

[Recommend no] Dungeon Brutes break doors. Lantern Wraiths hold their range and search, then follow through a door a Brute has broken. That gives clear roles (brute breaches, wraith zones), and doors buy real time against wraiths.

## 4. Coming up (no action needed yet)
- **NSC-078 prop art.** Revision 3 is committed. Its Codex check found fixable scope issues, and revision 4 is next. Your PixelLab spend go is needed only before the style pilot starts.
- **NSC-015 melee enemy.** It's with the Decomposition Agent. Split 2 still waits on your earlier questions: body blocking, wind-up movement, and what a defeated enemy looks like and whether it still collides.
