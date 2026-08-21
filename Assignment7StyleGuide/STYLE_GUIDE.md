# No Safe Circle — Style Guide

## Purpose

This guide defines the player-facing writing style for **No Safe Circle**. It is intended for AI-generated gameplay text such as spell tooltips, door tutorials, failure hints, short UI messages, and other concise in-game guidance.

The canonical GDD remains the authority for mechanics, controls, numbers, progression, room structure, enemy behavior, and lore. This style guide does not replace the GDD and must not be used to invent missing game facts.

The Style Evaluator should judge whether generated content sounds like **No Safe Circle** while preserving the meaning supported by the GDD.

---

## Style Principle

**No Safe Circle is about temporary control under continuing pressure.**

The player is a vulnerable wizard who can create short tactical opportunities with powerful magic, but no action should make the player sound permanently safe, unstoppable, or heroic in a conventional power-fantasy sense.

Player-facing copy should make the game feel:

- tense;
- tactical;
- restrained;
- immediate;
- mechanically readable;
- dark-fantasy without becoming flowery or lore-heavy.

The writing should reinforce the central idea that **safety is temporary**.

---

# 1. Tone and Player Experience

## NSC-TONE-01 — Tense, Tactical, Restrained

Player-facing text should use direct tactical language.

Prefer:

- create space;
- keep moving;
- slow pursuit;
- buy time;
- break away;
- reach the door;
- prepare a charge;
- watch the previous doorway;
- use the opening.

Avoid:

- triumphant heroism;
- congratulatory language;
- exaggerated empowerment;
- jokes or playful banter;
- melodramatic fantasy narration;
- language that makes danger sound trivial.

### Good

> Knock enemies back to create room to move.

### Bad

> Unleash your unstoppable power and send the pathetic horde flying!

---

## NSC-TONE-02 — Powerful Briefly, Vulnerable Immediately Afterward

The wizard may feel powerful for short moments, but generated text should preserve vulnerability and pressure.

Do not describe the player as:

- unstoppable;
- invincible;
- dominant;
- completely protected;
- able to control the battlefield indefinitely.

Strong actions should still sound like **temporary opportunities**, not permanent control.

### Good

> Frost Field slows the chase and can create time to reposition.

### Bad

> Frost Field gives you complete control of the room.

---

## NSC-TONE-03 — Safety Is Temporary

Locked doors, distance, crowd control, and positioning create recovery windows. They do not erase danger.

Avoid phrases such as:

- completely safe;
- permanently safe;
- enemies are gone;
- nothing can reach you;
- the threat is over.

When safety is mentioned, prefer language such as:

- temporary safety;
- recovery time;
- breathing room;
- a short opening;
- time before pursuers return.

---

# 2. Vocabulary, Naming, and World Canon

## NSC-CANON-01 — Use Established Game Terms

Use the canonical names established by the GDD when referring to game systems.

### Player

- wizard

Do not invent player classes or titles such as:

- Archmage;
- Battlemage;
- Sorcerer King;
- Ember Knight.

### Core Abilities

- Fireball
- Charged Fireball
- Frost Field
- Force Wave

Do not rename abilities for flavor.

### Core Enemies

- Melee Enemy
- Ranged Enemy

When the enemy type matters mechanically, preserve that distinction rather than replacing it with a generic term such as *monster* or *pursuer*.

### Door States

Use the correct state when relevant:

- sealed door;
- opened door;
- locked door;
- broken door.

Do not blur these states when the distinction affects the player's decision.

---

## NSC-CANON-02 — Do Not Invent Lore

Do not add unsupported:

- factions;
- gods;
- kingdoms;
- guilds;
- named NPCs;
- quests;
- artifacts;
- character backstories;
- spell schools;
- currencies;
- loot systems;
- dialogue lore;
- dungeon history.

Dark-fantasy atmosphere may be expressed through concise wording, but new worldbuilding is not allowed unless the canonical GDD explicitly establishes it.

### Bad

> The Ember Order taught every Archmage to use Force Wave against the servants of the Ash King.

This invents a faction, title, and antagonist.

---

## NSC-CANON-03 — Preserve Canonical Area Names

When a generated item specifically refers to a dungeon area, use its canonical name:

1. Ruined Entry
2. Bone Archive
3. Chapel of Ash
4. Lower Vault
5. Final Room

Do not invent replacement room names.

---

# 3. Mechanical Framing and Precision

## NSC-MECH-01 — Preserve Tradeoffs

No Safe Circle is built around tactical tradeoffs.

Do not turn a situational tool into a universally correct strategy.

For example:

- Force Wave may be used to escape a surround or preserved for a door attempt.
- Frost Field can create an opening but does not guarantee safety.
- Charged Fireball rewards preparation but becomes unsafe under pressure.
- Escape is valid, but enemies left alive can remain a later threat.

Avoid instructions such as:

- always save Force Wave for the door;
- always kill every enemy;
- Frost Field guarantees a safe charge;
- never flee;
- always charge Fireball.

---

## NSC-MECH-02 — Preserve Qualifiers

Do not silently strengthen qualified rules.

Words such as:

- may;
- can;
- typically;
- about;
- later;
- partial;
- temporary;

carry design meaning.

Do not convert them into:

- always;
- exactly;
- guaranteed;
- instantly;
- permanently;
- completely.

### Example

If the GDD says an encounter typically allows **about one meaningful Force Wave use**, do not rewrite that as:

> Force Wave can only be used once per room.

---

## NSC-MECH-03 — Do Not Add Unsupported Effects

Generated text must not add mechanics merely because they sound plausible.

Examples of prohibited unsupported additions include:

- Frost Field freezing or immobilizing enemies;
- Force Wave dealing damage or stunning enemies;
- locked doors destroying pursuers;
- enemies disappearing between rooms;
- invented damage values;
- invented cooldown durations;
- invented regeneration rates;
- invented status effects.

If a fact is not supported by the content task or canonical evidence, omit it rather than guessing.

---

## NSC-MECH-04 — Preserve Enemy-Specific Limitations

If a rule applies specifically to Melee Enemies or Ranged Enemies, retain that distinction.

Examples:

- Frost Field strongly disrupts melee pursuit, while Ranged Enemies can still attack.
- Force Wave is useful at short range and is a poor answer to distant ranged pressure.
- Ranged attacks pressure the player to keep moving while Melee Enemies close distance.

Do not generalize enemy-specific behavior when doing so changes the tactical meaning.

---

## NSC-MECH-05 — Persistent Threats Remain Persistent

Surviving enemies are not automatically removed when the player advances.

Copy concerning doors or later rooms should preserve the idea that surviving enemies can remain a threat and eventually break through locked doors.

Do not imply that entering the next room resets the encounter or deletes surviving enemies.

---

# 4. Formatting and Readability

## NSC-FORMAT-01 — Write for Gameplay, Not a Lore Book

Player-facing text must be readable during play.

Prefer:

- one short paragraph;
- one or two short sentences;
- clear verbs;
- immediate tactical meaning.

Avoid:

- long exposition;
- multi-paragraph lore dumps;
- ornate scene-setting;
- unnecessary backstory;
- repeated explanation.

---

## NSC-FORMAT-02 — Respect the Requested Content Type

The format should match its gameplay purpose.

### Spell Tooltip

Briefly explain:

- what the ability does;
- its important tactical use;
- a meaningful limitation or tradeoff when necessary.

### Door Tutorial

Explain the immediate interaction or consequence without turning it into a full mechanic essay.

### Failure Hint

Teach a readable lesson without insulting or blaming the player.

Failure hints should help the player understand what happened and what decision space exists next time.

---

## NSC-FORMAT-03 — Respect the Supplied Word Limit

If a content request supplies a maximum word count, treat it as a hard formatting requirement.

Do not exceed the limit to add flavor or explanation.

Concision must not remove a limitation when that omission would make the surviving text misleading.

---

## NSC-FORMAT-04 — No Meta Commentary

Player-facing text must not mention:

- the GDD;
- prompts;
- AI;
- agents;
- evaluators;
- refiners;
- retrieval;
- style rules;
- test cases.

Only the actual game-facing copy belongs in the final content.

---

# 5. Evaluation Guidance

The Style Evaluator should score the candidate against the rules above.

The evaluator is not a general writing critic. It should judge whether the text fits **No Safe Circle**.

A high score requires:

- correct No Safe Circle tone;
- established vocabulary and naming;
- no invented lore;
- preserved tactical tradeoffs and qualifiers;
- no unsupported mechanical claims;
- appropriate in-game formatting and length.

A low score should identify concrete rule violations by rule ID and explain why they conflict with this guide.

Minor wording preference alone should not reduce the score substantially if the candidate is already faithful, concise, and clear.

---

# 6. Score Interpretation

Use a **1–10 score**.

- **10** — Fully consistent with the style guide. No meaningful revision needed.
- **8–9** — Strong fit with only minor style drift.
- **6–7** — Recognizably No Safe Circle, but one or more meaningful violations should be corrected.
- **4–5** — Significant tone, canon, mechanical-framing, or formatting problems.
- **1–3** — Fundamentally inconsistent with No Safe Circle or dominated by invented/exaggerated content.

For Assignment 7's automated correction loop, a candidate is accepted only when it reaches the configured target score. The evaluator must always provide both a numerical **SCORE** and a specific **REASON** so the Refiner has actionable feedback.

---

# 7. Short Reference

When uncertain, favor this pattern:

**Direct action + tactical purpose + limitation/consequence.**

Example:

> Slow the melee group with Frost Field to create space, but keep moving — Ranged Enemies can still attack.

Avoid this pattern:

**Heroic flourish + invented lore + guaranteed result.**

Example:

> Invoke the ancient Frost Sigil and freeze every servant of the Ash King, making the chamber completely safe.
