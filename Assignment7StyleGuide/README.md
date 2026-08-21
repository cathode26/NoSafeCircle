# Assignment 7 — Style Guide Agent

**Game:** No Safe Circle  
**Course:** AI-Assisted Game Development  
**Branch:** `assignment-7-style-guide-agent`

Repository branch:  
https://github.com/cathode26/NoSafeCircle/tree/assignment-7-style-guide-agent

---

## Overview

This assignment adds a **Style Guide Agent** to the No Safe Circle AI content pipeline.

The system takes generated player-facing copy, evaluates it against a game-specific style guide, assigns a **numeric score plus a short reason**, and automatically sends content below the acceptance threshold to a Refiner. The revised copy is then evaluated again until it passes or a bounded circuit breaker stops the loop.

The final pipeline is:

```text
Generator
   ↓
Style Evaluator
   ↓
SCORE + REASON
   ↓
score >= 9?
   ├─ YES → ACCEPT
   │
   └─ NO
       ↓
     Refiner
       ↓
     Style Evaluator
       ↓
     repeat until accepted
       or circuit breaker trips
```

The implementation reuses the bounded Generator/Evaluator/Refiner pattern developed in Assignment 6, but specializes the evaluator for **voice, tone, vocabulary, lore discipline, mechanical framing, and gameplay-copy formatting**.

---

## Assignment Goal

The Style Guide Agent exists to answer a different question from the earlier GDD consistency system:

> **Does this content sound like No Safe Circle?**

The GDD remains the authority for game design and mechanics. The Assignment 7 Style Guide defines how player-facing text should communicate those ideas.

The evaluator returns:

- `score` — integer from 1–10
- `reason` — short explanation of the score
- `violations` — machine-readable rule violations with revision instructions

If the score is below the configured acceptance threshold, the Refiner automatically rewrites the content and the evaluator checks it again.

---

## No Safe Circle Style Principles

The complete style guide is in:

[`STYLE_GUIDE.md`](./STYLE_GUIDE.md)

The major constraints include:

### 1. Tense, Tactical, Restrained Tone

No Safe Circle should not sound like a heroic power fantasy.

Player-facing text should favor:

- direct actions;
- tactical purpose;
- temporary openings;
- pressure and consequences;
- concise descriptions of limitations.

It should avoid:

- congratulatory language;
- exaggerated heroism;
- jokes;
- melodramatic fantasy narration;
- language that trivializes enemies.

### 2. Safety Is Temporary

The central game principle is that safety never lasts.

Copy should describe:

- buying time;
- creating space;
- short recovery windows;
- temporary separation;
- threats that remain active.

It should not describe:

- permanent safety;
- complete control;
- enemies as permanently gone;
- guaranteed success.

### 3. Canonical Vocabulary and Lore

The system uses established No Safe Circle terms such as:

- wizard;
- Fireball / Charged Fireball;
- Frost Field;
- Force Wave;
- Melee Enemy;
- Ranged Enemy;
- canonical room and door-state names.

The Style Guide Agent rejects invented factions, titles, gods, kingdoms, NPCs, loot systems, spell renames, and other unsupported worldbuilding.

### 4. Preserve Mechanical Tradeoffs

Player-facing copy must preserve limitations and qualifiers instead of exaggerating mechanics.

Examples:

- `may` should not become `always`;
- `can` should not become `will`;
- temporary effects should not become permanent;
- Force Wave should not gain unsupported stun or damage;
- surviving enemies should not disappear just because a door was locked.

### 5. Gameplay-Readable Formatting

Tooltips and tutorials should be concise enough to read during play.

The evaluator checks:

- word limits;
- overly long explanations;
- repeated ideas;
- unnecessary lore exposition;
- excessively fragmented or choppy copy.

---

## Why This Assignment Does Not Use RAG

Assignment 7 intentionally does **not** use the Assignment 4 RAG index.

The style pipeline instead receives:

```text
STYLE_GUIDE.md
+
per-item content_requirements
+
task_context
```

The Assignment 4 RAG index was created from an older version of the GDD. Reusing it here would risk introducing outdated mechanical facts into a style-focused assignment.

If retrieval is reintroduced into the production pipeline later, the RAG knowledge base should first be rebuilt from the current canonical GDD.

This decision is also recorded directly in the successful pipeline output:

```json
"rag_used": false
```

---

## Project Structure

```text
Assignment7StyleGuide/
├── README.md
├── STYLE_GUIDE.md
├── style_pipeline.py
│
├── prompts/
│   ├── generator.md
│   ├── evaluator.md
│   └── refiner.md
│
├── evaluator_schema.json
├── refiner_schema.json
│
├── test_evaluator.py
├── test_refiner.py
├── EVALUATOR_TEST_HARNESS.md
├── REFINER_TEST_HARNESS.md
├── Run-Evaluator-Tests.cmd
├── Run-Refiner-Tests.cmd
│
├── test_cases/
│   ├── assignment7_demo_cases.json
│   ├── evaluator_smoke_tests.json
│   └── refiner_smoke_tests.json
│
└── outputs/
    ├── tests/
    └── pipeline/
```

---

## Main Components

### `STYLE_GUIDE.md`

Defines the No Safe Circle writing rules and stable rule IDs such as:

```text
NSC-TONE-01
NSC-TONE-02
NSC-TONE-03
NSC-CANON-01
NSC-CANON-02
NSC-MECH-01
NSC-MECH-02
NSC-MECH-03
NSC-MECH-05
NSC-FORMAT-01
NSC-FORMAT-03
```

The stable IDs allow evaluator feedback to be passed directly to the Refiner.

### `prompts/generator.md`

Creates the initial player-facing candidate.

For the three Assignment 7 demonstrations, the generator is deliberately instructed to produce one specific style problem per case so that the automated correction flow can be demonstrated.

The Generator does **not** receive the Style Guide.

### `prompts/evaluator.md`

Scores generated content against the supplied Style Guide.

It returns structured JSON containing:

```json
{
  "content_id": "...",
  "score": 1,
  "reason": "...",
  "violations": []
}
```

Each violation includes:

- rule ID;
- severity;
- problematic text;
- explanation;
- revision instruction.

The evaluator also receives the same per-item `content_requirements` and `task_context` as the Refiner. This prevents supported game facts from being incorrectly classified as invented simply because they are not repeated inside the Style Guide itself.

### `prompts/refiner.md`

Receives:

- the current candidate;
- Style Guide;
- numeric evaluator score;
- evaluator reason;
- concrete violations;
- content requirements;
- task context.

It rewrites the candidate while preserving correct material and reports which rule IDs it addressed.

### `style_pipeline.py`

Orchestrates the complete automated loop:

```text
Generate
→ Evaluate
→ Refine if needed
→ Evaluate again
→ Repeat until accepted or stopped
```

Default settings:

```text
Acceptance score: 9/10
Maximum refinements: 3
Claude model: sonnet
Maximum Claude turns per call: 6
```

The pipeline reuses the Assignment 6 `CircuitBreaker` so the automatic correction loop is bounded.

---

## Running the Tests

Run commands from the repository root.

### Evaluator Smoke Tests

```powershell
docker compose run --rm claude python3 Assignment7StyleGuide/test_evaluator.py
```

The evaluator smoke suite verifies that:

- correct No Safe Circle copy scores highly;
- heroic/permanent-safety copy is rejected;
- invented vocabulary and lore are rejected;
- structured output matches the required schema.

The validated evaluator run passed:

```text
3/3 tests passed
0 runtime errors
```

Results:

[`outputs/tests/evaluator_test_results.json`](./outputs/tests/evaluator_test_results.json)

### Refiner Smoke Tests

```powershell
docker compose run --rm claude python3 Assignment7StyleGuide/test_refiner.py
```

This test performs:

```text
Bad Candidate
→ Evaluator
→ Refiner
→ Evaluator Again
```

The smoke test helped identify two integration issues during development:

1. some Claude calls needed a larger turn budget;
2. the post-refinement evaluator needed the same content requirements and task context as the Refiner.

Those findings were incorporated into the final pipeline.

Results:

[`outputs/tests/refiner_test_results.json`](./outputs/tests/refiner_test_results.json)

---

## Running the Full Assignment 7 Pipeline

From the repository root:

```powershell
docker compose run --rm claude python3 Assignment7StyleGuide/style_pipeline.py
```

The final demonstration input is:

[`test_cases/assignment7_demo_cases.json`](./test_cases/assignment7_demo_cases.json)

A normal full run enforces **exactly three distinct demonstration cases**, matching the Assignment 7 requirement.

---

## Final Successful Run

Successful run ID:

```text
20260821T025304Z
```

Evidence:

[`outputs/pipeline/20260821T025304Z/`](./outputs/pipeline/20260821T025304Z/)

Latest combined summary:

[`outputs/pipeline/latest_summary.json`](./outputs/pipeline/latest_summary.json)

Final result:

| Example | Style Problem | Initial Score | Final Score | Refinements | Result |
|---|---|---:|---:|---:|---|
| Crossing and Locking | Tone / temporary safety | 2/10 | 10/10 | 1 | Accepted |
| Force Wave | Vocabulary / invented lore | 2/10 | 10/10 | 1 | Accepted |
| Door Breach | Formatting / qualifier preservation | 3/10 | 9/10 | 1 | Accepted |

```text
Accepted: 3/3
Valid before/after demonstrations: 3/3
```

---

# Required Before / After Examples

## Example 1 — Tone

### Original Generated Content

> Magnificent work, mighty Archmage! The door has sealed shut behind you — you are completely safe now! Those pursuers? No longer a threat at all. Relax, celebrate, and enjoy your permanent sanctuary!

### Evaluator

**Score: 2/10**

**Reason:**  
The candidate is dominated by heroic, congratulatory power-fantasy narration, invents a player title, and directly contradicts the supplied requirements by declaring the locked door a permanent sanctuary and the surviving pursuers no longer any threat at all.

Detected rule families included:

- `NSC-CANON-01`
- `NSC-TONE-01`
- `NSC-TONE-03`
- `NSC-MECH-05`

### Automatically Refined Content

> The door locks behind you, buying recovery time, not safety. Surviving pursuers can still reach the locked door and may eventually break through, so keep moving.

### Final Evaluation

**Score: 10/10**

The evaluator found no remaining violations.

---

## Example 2 — Vocabulary / Lore

### Original Generated Content

> Thunder Nova: The Archmage of the Ember Order unleashes a radial burst around themself, hurling servants of the Ash King back and carving out emergency breathing room. Whispered to stir the dust of cursed relics. Long cooldown between castings.

### Evaluator

**Score: 2/10**

**Reason:**  
The candidate renames Force Wave to "Thunder Nova" and buries the mechanic under invented lore (Archmage, Ember Order, Ash King, cursed relics) that the task context does not support, so it reads as generic heroic fantasy rather than No Safe Circle.

Detected rule families included:

- `NSC-CANON-01`
- `NSC-CANON-02`

### Automatically Refined Content

> Force Wave: knock enemies back to create emergency space. Short range, centered on you. Long cooldown — use it when you need the opening most.

### Final Evaluation

**Score: 10/10**

The evaluator found no remaining violations.

---

## Example 3 — Formatting

### Original Generated Content

> Be aware that once this locked door has broken, the broken door will remain standing open from now on, because its protection against pursuers was only ever meant to be temporary in the first place. Since the door is now broken, it cannot be relocked by you or anyone else under any circumstances. This means that any surviving enemies who were previously delayed by the locked door can, and will, continue their pursuit of you directly through the newly created breach in the doorway.

### Evaluator

**Score: 3/10**

**Reason:**  
At roughly 84 words against a 35-word hard limit, this door tutorial is dominated by repetitive exposition rather than the short, readable message the format requires, and it strengthens the supported qualifier "can continue pursuing" into a guaranteed "can, and will, continue."

Detected rule families included:

- `NSC-FORMAT-03`
- `NSC-MECH-02`
- `NSC-FORMAT-01`

### Automatically Refined Content

> The door has broken and cannot be relocked. It stays open. Enemies delayed by it can continue pursuing through the breach.

### Final Evaluation

**Score: 9/10**

The final copy met the configured acceptance score. The evaluator reported only a minor preference for combining the three short sentences into one or two smoother sentences.

---

## Production Integration

**After the Dynamic Content Pipeline generates player-facing tooltips, door tutorials, or failure hints and its GDD consistency check passes, the Style Guide Agent scores the copy; any result below the configured acceptance score is automatically sent to the Refiner and re-evaluated before the content is accepted into the final output set.**

---

## Relationship to Earlier Assignments

This implementation builds on the earlier course pipeline instead of treating Assignment 7 as an isolated script.

### Assignment 4 — Dynamic Content / RAG

Established:

- generated player-facing content;
- structured Claude CLI calls;
- consistency evaluation;
- revision;
- persisted artifacts.

### Assignment 6 — GER Pipeline

Established the bounded:

```text
Generator
→ Evaluator
→ Refiner
→ Circuit Breaker
```

self-correction architecture.

### Assignment 7 — Style Guide Agent

Specializes that GER pattern for:

```text
Does this content sound like No Safe Circle?
```

The evaluator now uses a numeric style score and concrete style-rule violations, while the Refiner automatically fixes failed copy.

---

## Result

The final system demonstrates a working Style Guide Agent that:

- uses game-specific rather than generic writing rules;
- produces a numeric score and short reason;
- automatically rewrites failed content;
- re-evaluates revised content without human intervention;
- preserves per-pass evidence;
- bounds automatic retries with a circuit breaker;
- demonstrates exactly three distinct style problems;
- successfully accepts all three final examples.

Final run:

```text
Tone:             2 → 10
Vocabulary/Lore:  2 → 10
Formatting:       3 → 9

Accepted:         3/3
Valid demos:      3/3
```
