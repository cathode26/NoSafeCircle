# No Safe Circle — Dynamic Content Pipeline

Assignment 4 extends the **No Safe Circle** capstone with a small RAG-based content pipeline. The canonical source is the game design document, converted into a 39-chunk knowledge base. The pipeline retrieves relevant GDD chunks, generates player-facing content, runs a consistency critic, and revises flagged output.

## What the pipeline generates

The game needs three groups of player-facing content:

1. **Spell tooltips** — Tap Fireball, Charged Fireball, Frost Field, and Force Wave.
2. **Door tutorials** — opening a sealed door, crossing/locking, health recovery, breach behavior, and persistent pursuit.
3. **Failure hints** — poor positioning, low mana, Force Wave timing, and waiting too long.

Final generated files are in:

- `DynamicContentPipeline/outputs/final/spell_tooltips.json`
- `DynamicContentPipeline/outputs/final/door_tutorial.json`
- `DynamicContentPipeline/outputs/final/failure_hints.json`

## Pipeline

```text
No Safe Circle GDD
    ↓
39 canonical RAG chunks
    ↓
content request / query
    ↓
deterministic retrieval
    ↓
Claude content generator
    ↓
initial output
    ↓
consistency critic
    ↓
targeted revisor
    ↓
final output
    ↓
final consistency validation
```

The retriever is deterministic and records the query, ranked chunk IDs, scores, matched terms, and source locations. The generator is instructed to use only retrieved canonical GDD evidence and not invent mechanics, numbers, controls, progression, or lore.

## RAG example: Frost Field

A first Frost Field query retrieved the **Final Room** chunk ahead of the dedicated Frost Field mechanics chunk:

```text
Query:
What does Frost Field do, what tactical problem does it solve,
and what limitations apply against melee and ranged enemies?

Rank 1: nsc-gdd-019 — Final Room — score 65.2967
Rank 2: nsc-gdd-010 — Frost Field interactions and limitations — score 62.0628
```

That produced wording that said Frost Field slowed **“anyone caught inside.”** The GDD only establishes its behavior against enemies, so the query was tightened to focus directly on Frost Field's interactions and limitations against melee and ranged enemies. The dedicated Frost Field chunk then ranked first.

Final output:

> A field of icy ground heavily slows enemies caught inside. Strongest against melee groups, stretching their formation—but it costs real mana and won't guarantee a safe charge. Ranged enemies are slowed too, yet can still fire, so keep moving.

This is the clearest example of a concrete retrieval/prompt adjustment improving the generated content.

## Query → retrieved chunk → output example

**Query**

```text
What happens when a locked door breaks, and what can the player
and surviving enemies do after the breach?
```

**Top retrieved chunk**

`nsc-gdd-022 — Door and pursuit rules: breach, persistence, and enemy cap`

The chunk states that a broken door remains open, cannot be relocked, the player cannot travel backward through it, and surviving enemies can continue forward.

**Generated output**

> The door broke. It stays open now, and it can't be locked again. There's no going back through it — whatever survived the fight is coming through.

This keeps the generated tutorial directly anchored to the game rules rather than generic fantasy-game advice.

## What the critic caught

The first critic pass marked **8 of 13 items for revision**. Examples included:

- Frost Field said it slowed **“anything”** instead of limiting the claim to enemies.
- Force Wave changed **“typically about one meaningful use”** into an absolute one-use rule.
- A door tutorial said to **“stay safe,”** implying safety that the GDD does not guarantee.
- A door tutorial said pursuers **“immediately”** attack a locked door even though the GDD only says they begin attacking it.
- A low-mana hint recommended waiting without mentioning that locked doors continue losing durability.
- Later validation also caught subtler drift introduced during revision, including overly prescriptive strategy and dropping qualifiers such as “may,” “typically,” or “later encounters.”

The revisor was updated so later critic feedback refines the **current final text** instead of restarting from the original generation. This prevents a later revision from accidentally reintroducing an earlier problem.

## Final validation

The final consistency critic is version **1.2** and validates the final outputs against their retrieved canonical GDD chunks.

Current final status:

- Spell tooltips: **4 / 4 pass**
- Door tutorials: **5 / 5 pass**
- Failure hints: **4 / 4 pass**
- **Total: 13 / 13 pass**

Final critic reports are in:

- `DynamicContentPipeline/outputs/critic/final_validation/spell_tooltips_final_critic.json`
- `DynamicContentPipeline/outputs/critic/final_validation/door_tutorial_final_critic.json`
- `DynamicContentPipeline/outputs/critic/final_validation/failure_hints_final_critic.json`

## Does it sound like No Safe Circle?

Yes. The final copy is short, tactical, and focused on the game's core idea that **safety is temporary**. The text emphasizes creating space, managing mana, making risky timing decisions, and dealing with enemies that remain a threat across rooms.

The strongest improvement from the critic/revision loop was removing language that made the player sound more powerful or safer than the GDD supports. The final wording preserves uncertainty and tradeoffs instead of turning them into guaranteed rules or a single “correct” strategy.

## Important files

```text
DynamicContentPipeline/
├── knowledge_base/No_Safe_Circle_GDD_RAG.json
├── retrieval.py
├── generate_content.py
├── consistency_check.py
├── revise_content.py
├── content_requests/
├── prompts/
├── tests/
└── outputs/
```

The canonical game-design source referenced by the RAG chunks is:

`Docs/GDD/No_Safe_Circle_GDD.md`
