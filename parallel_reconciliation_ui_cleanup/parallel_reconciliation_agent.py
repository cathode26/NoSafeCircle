from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import reconciliation_agent as base


# ============================================================
# PARALLEL RECONCILIATION CONFIG
# ============================================================

WORKER_MODEL = os.environ.get("RECONCILIATION_WORKER_MODEL", base.MODEL)
MAX_PARALLEL_WORKERS = int(
    os.environ.get("RECONCILIATION_PARALLEL_WORKERS", "6")
)
DEFAULT_WORKER_TIMEOUT_SECONDS = int(
    os.environ.get("RECONCILIATION_WORKER_TIMEOUT_SECONDS", "720")
)


# ============================================================
# CONSOLE OUTPUT
# ============================================================

CONSOLE_WIDTH = 72
CONSOLE_LINE = "=" * CONSOLE_WIDTH
CONSOLE_SUBLINE = "-" * CONSOLE_WIDTH
_CONSOLE_LOCK = threading.Lock()


def print_block(*lines: str, line: str = CONSOLE_LINE) -> None:
    """Print one complete block atomically so parallel workers cannot interleave."""
    body = "\n".join(str(value) for value in lines)
    with _CONSOLE_LOCK:
        print()
        print(line)
        if body:
            print(body)
        print(line)
        print(flush=True)


def print_event(message: str) -> None:
    """Print one worker event as an atomic line with spacing."""
    with _CONSOLE_LOCK:
        print(message)
        print(flush=True)


# ============================================================
# WORKER OUTPUT SCHEMA
# ============================================================

OVERLAY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "owner_key": {"type": "string"},
        "acceptance_criteria": {
            "type": "array",
            "items": base.GDD_EVIDENCE_SCHEMA,
        },
        "validation_requirements": {
            "type": "array",
            "items": base.GDD_EVIDENCE_SCHEMA,
        },
        "reason": {"type": "string"},
    },
    "required": [
        "owner_key",
        "acceptance_criteria",
        "validation_requirements",
        "reason",
    ],
}

WORKER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "domain": {"type": "string"},
        "desired_state_summary": {"type": "string"},
        "current_state_summary": {"type": "string"},
        "major_findings": {
            "type": "array",
            "items": {"type": "string"},
        },
        "work_items": {
            "type": "array",
            "items": base.WORK_ITEM_SCHEMA,
        },
        "requirement_overlays": {
            "type": "array",
            "items": OVERLAY_SCHEMA,
        },
        "non_code_requirements": {
            "type": "array",
            "items": base.NON_CODE_SCHEMA,
        },
        "deferred_or_excluded": {
            "type": "array",
            "items": base.DEFERRED_SCHEMA,
        },
        "unresolved_questions": {
            "type": "array",
            "items": base.UNRESOLVED_SCHEMA,
        },
        "files_reviewed": {
            "type": "array",
            "items": {"type": "string"},
        },
        "historical_sources_reviewed": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "domain",
        "desired_state_summary",
        "current_state_summary",
        "major_findings",
        "work_items",
        "requirement_overlays",
        "non_code_requirements",
        "deferred_or_excluded",
        "unresolved_questions",
        "files_reviewed",
        "historical_sources_reviewed",
    ],
}


@dataclass(frozen=True)
class DomainSpec:
    slug: str
    title: str
    scope: str
    repo_focus: str
    prior_keys: tuple[str, ...]
    max_turns: int


# These are routing hints derived from the last successful/refined reconciliation
# (20260820T203258Z-3b04bcc8). They are NOT canon and are NOT evidence.
#
# Workers must re-derive current truth from the GDD/repository. Stable keys are
# retained when the same responsibility still exists so cross-domain references
# remain cheap and deterministic.
DOMAINS: tuple[DomainSpec, ...] = (
    DomainSpec(
        slug="player_core",
        title="Player Core Systems",
        scope=(
            "Player movement/input, Player Health, Player Mana, player position, "
            "movement-restriction ownership, health/mana feedback, player-side "
            "reset entry points, and player-core validation."
        ),
        repo_focus=(
            "Start with current player prototype evidence under "
            "Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMovement.cs, "
            "PlayerHealth.cs, PlayerMana.cs, PlayerManaUI.cs, relevant player "
            "tests, the current prototype scene, and InputSystem_Actions.inputactions "
            "only when needed. Do not broadly scan enemy/world content."
        ),
        prior_keys=(
            "player",
            "player-movement",
            "player-health",
            "player-mana",
        ),
        max_turns=16,
    ),
    DomainSpec(
        slug="wizard_combat",
        title="Wizard Combat and Spells",
        scope=(
            "Fireball, Frost Field casting/player-facing field feedback, Force Wave, "
            "spell-local charge/cast/cooldown/active state, mana consumption contracts, "
            "charged-Fireball movement restriction consumption, enemy damage/status/"
            "displacement interfaces consumed by spells, victory disable behavior, and "
            "spell-local restart ownership."
        ),
        repo_focus=(
            "Inspect only current player/spell/combat code and directly consumed "
            "interfaces under Assets/NoSafeCircle/DoorPrototype/Scripts plus relevant "
            "tests/serialized evidence when it exists. Do not re-audit all enemy/world code."
        ),
        prior_keys=(
            "combat",
            "fireball",
            "frost-field",
            "force-wave",
        ),
        max_turns=16,
    ),
    DomainSpec(
        slug="enemy_state",
        title="Enemy State, Persistence, and Shared Effects",
        scope=(
            "The Enemies feature parent, Active Enemy Registry, Enemy Health/Defeat, "
            "enemy persistent-object bookkeeping, defeat-to-registry handoff, Frost "
            "slowdown apply/restore, forced displacement, state hand-back, and reset "
            "ownership for these shared enemy capabilities."
        ),
        repo_focus=(
            "Inspect only current enemy/shared-state/status code under "
            "Assets/NoSafeCircle/DoorPrototype/Scripts and directly relevant tests/"
            "serialized evidence. Do not own pursuit archetype behavior or door lifecycle."
        ),
        prior_keys=(
            "enemies",
            "active-enemy-registry",
            "enemy-health-damage-defeat",
            "enemy-status-effect-displacement",
        ),
        max_turns=16,
    ),
    DomainSpec(
        slug="enemy_behavior",
        title="Enemy Pursuit and Attack Behavior",
        scope=(
            "Detection, pursuit, target loss, last-known-position search, bounded "
            "randomized search/wander, reacquisition, Melee Enemy, Ranged Enemy, "
            "slow telegraphed ranged attacks, line-of-sight/projectile occlusion, "
            "locked-door enemy attack initiation, and locomotion/navigation consumption."
        ),
        repo_focus=(
            "Inspect current enemy pursuit/attack/archetype code under "
            "Assets/NoSafeCircle/DoorPrototype/Scripts and directly relevant tests/"
            "scene evidence. Treat Enemy Health/Registry/status and Door durability as "
            "cross-domain owners, not work to duplicate."
        ),
        prior_keys=(
            "enemy-pursuit-search-foundation",
            "melee-enemy",
            "ranged-enemy",
            "locked-door-enemy-attack",
        ),
        max_turns=18,
    ),
    DomainSpec(
        slug="doors",
        title="Doors and Interaction",
        scope=(
            "The Doors feature parent, cursor-targeted opening, arm's-reach check, "
            "selection latch/interruption behavior, shared doorway-crossing state, "
            "close/lock, Player Health restore request, runtime durability, door damage "
            "receive interface, locked-to-broken lifecycle, forward-only progression, "
            "door feedback, and semantic-state publication to navigation."
        ),
        repo_focus=(
            "Start with DoorInteractable.cs, PlayerInteractionController.cs, "
            "DoorInteractionPlayModeTests.cs, the current DoorPrototype scene/prefab "
            "evidence, and only directly required shared interfaces."
        ),
        prior_keys=(
            "doors",
            "door-open-interaction",
            "doorway-crossing-state",
            "door-close-lock-break-lifecycle",
        ),
        max_turns=16,
    ),
    DomainSpec(
        slug="world_foundations",
        title="World and Unity Foundations",
        scope=(
            "The World feature parent, fixed isometric camera, approved Tilemap/AI "
            "Navigation packages, gameplay navigation/locomotion foundation, semantic "
            "door-state to enemy-walkability passability interface, Tilemap/"
            "SpriteRenderer visual foundation, visual/gameplay separation, sorting, "
            "and current scene/world integration evidence."
        ),
        repo_focus=(
            "Start with DoorPrototypeSceneBuilder.cs, DoorPrototype.unity, "
            "IsometricCameraFollow.cs, relevant editor tests, ProjectSettings when "
            "needed, Packages/manifest.json, and Packages/packages-lock.json. Do not "
            "author the five named spaces or encounter content."
        ),
        prior_keys=(
            "world",
            "fixed-isometric-camera",
            "tilemap-navigation-package-configuration",
            "gameplay-navigation-locomotion",
            "world-visual-foundation",
        ),
        max_turns=20,
    ),
    DomainSpec(
        slug="content_encounters",
        title="Floor Content and Encounters",
        scope=(
            "Five-room/five-space deferred content authoring, Dungeon Encounters feature "
            "parent, encounter-admission active-enemy-cap enforcement, encounter placement/"
            "composition deferred authoring, named-room tactical/validation requirements, "
            "three-to-eight encounter-size success criteria, and the relationship between "
            "authored room spaces and later concrete encounter-placement descendants."
        ),
        repo_focus=(
            "Inspect current scene/content/encounter evidence only enough to determine "
            "what is actually authored versus deferred and whether encounter-cap runtime "
            "exists. Do not re-implement world foundations, registry internals, or enemy AI."
        ),
        prior_keys=(
            "five-room-content-authoring",
            "encounters",
            "encounter-admission-cap-enforcement",
            "dungeon-encounter-content-authoring",
        ),
        max_turns=14,
    ),
    DomainSpec(
        slug="run_lifecycle",
        title="Run Lifecycle and Victory",
        scope=(
            "Floor Run/Restart feature and orchestrator, current-owner restart bootstrap, "
            "full persistent-systems restart closure, zero-health trigger consumption, "
            "Win/Loss Conditions feature, final escape via shared doorway-crossing state, "
            "normal gameplay-input shutdown, You Escaped feedback, and cross-domain reset/"
            "victory dependencies."
        ),
        repo_focus=(
            "Inspect current reset/death/victory/player-position/door state evidence only "
            "as needed to determine which current owners exist. Rely on GDD ownership for "
            "future required participants rather than broadly re-scanning every subsystem."
        ),
        prior_keys=(
            "floor-run-restart",
            "floor-run-restart-bootstrap",
            "floor-run-restart-persistent-closure",
            "win-loss-conditions",
            "final-escape-victory",
        ),
        max_turns=18,
    ),
    DomainSpec(
        slug="global_pipeline",
        title="Delivery, Validation, and Pipeline Constraints",
        scope=(
            "The single no-safe-circle root, Delivery and Build feature, Windows build/"
            "scene registration, all typed non-code/delivery/pipeline requirements, "
            "Development Agent Ownership Invariants as process constraints, compile/"
            "validation/human-integration/source-control/minimal-context/retry/token rules, "
            "runtime-AI prohibition, all stretch/excluded scope, and GLOBAL validation "
            "overlays for Player Experience Success Criteria that belong on owners emitted "
            "by other workers."
        ),
        repo_focus=(
            "Inspect ProjectSettings/EditorBuildSettings.asset and package/current-project "
            "evidence only when needed for delivery/build or process/current-state claims. "
            "Do not duplicate gameplay implementations owned by other workers."
        ),
        prior_keys=(
            "no-safe-circle",
            "delivery-and-build",
            "windows-build-scene-registration",
        ),
        max_turns=16,
    ),
)

DOMAIN_BY_SLUG = {spec.slug: spec for spec in DOMAINS}
KNOWN_KEY_OWNER: dict[str, str] = {
    key: spec.slug
    for spec in DOMAINS
    for key in spec.prior_keys
}


# ============================================================
# CLAUDE WORKER
# ============================================================

def _invoke_worker(spec: DomainSpec) -> dict[str, Any]:
    canonical_prompt = base.load_prompt()

    routing_keys = "\n".join(f"- `{key}`" for key in spec.prior_keys)

    prompt = f"""
{canonical_prompt}

---

# PARALLEL DOMAIN OVERRIDE — {spec.title}

You are one of nine specialized reconciliation workers.

The canonical reconciliation instructions above remain authoritative for
source boundaries, evidence quality, ownership, dependency semantics,
requirement representation, execution scope, exclusive resources, and
anti-invention rules.

This override supersedes only the instruction to emit the COMPLETE final
reconciliation. Emit only your assigned domain.

## Assigned domain

{spec.scope}

## Repository focus

{spec.repo_focus}

## Routing hints from the previous successful/refined reconciliation

The following stable keys existed in the immediately previous refined candidate
and were assigned to this domain:

{routing_keys}

These keys are ROUTING HINTS ONLY.

They are NOT GDD evidence.
They are NOT repository evidence.
They are NOT permission to preserve stale work.

For each hinted key:
- keep the stable key when the same responsibility is still required/current;
- omit it if current GDD/repository truth no longer supports it, and explain why
  in `major_findings`;
- add new same-domain work when the current GDD requires something the previous
  candidate missed.

## Mandatory worker rules

1. Read the ENTIRE current GDD before deciding what belongs to this domain.
   One owner may be described in mechanics, feedback, win/loss, Player
   Experience Success Criteria, agent roles/invariants, and technical strategy.

2. Inspect only the repository areas needed for this domain. Do not perform a
   project-wide scan merely to be thorough.

3. Emit work only for this domain. Do not copy another owner's implementation
   into your work just because your system consumes it.

4. You MAY reference a concrete cross-domain prerequisite using its stable key
   when the GDD/current architecture establishes that prerequisite. Never target
   a feature dependency.

5. If a cross-domain contract is real but the concrete owner/key is genuinely
   uncertain, preserve the uncertainty rather than inventing ownership.

6. Do not emit another worker's known routed key. Cross-domain consumers refer
   to that key through `depends_on`; they do not duplicate it.

7. Preserve all relevant qualifiers: aiming model, timing, interruption,
   feedback/readability, persistent state, reset behavior, ownership, state
   handoff, telegraphing, range/distance relationships, and validation.

8. `files_reviewed` lists only approved GDD/current-project evidence paths
   actually inspected. Do not list reconciliation outputs or prompt files.

9. All workers except `global_pipeline` MUST return:
   - `non_code_requirements: []`
   - `deferred_or_excluded: []`
   - `requirement_overlays: []`

10. `global_pipeline` alone owns typed non-code/deferred records and may emit
    `requirement_overlays` that add GDD-backed acceptance/validation requirements
    to another worker's existing owner. It must NOT recreate that owner's work item.

11. Return only the worker-schema JSON.

12. Domain label MUST be exactly: `{spec.slug}`
""".strip()

    compact_schema = json.dumps(
        WORKER_SCHEMA,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    command = [
        "claude",
        "-p",
        "--model",
        WORKER_MODEL,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-turns",
        str(spec.max_turns),
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Read,Glob,Grep",
        "--allowedTools",
        "Read,Glob,Grep",
        "--disallowedTools",
        base.CLAUDE_DISALLOWED_TOOLS,
        "--json-schema",
        compact_schema,
        "--input-format",
        "text",
    ]

    print_block(
        f"[START] {spec.title}",
        f"  Routing : {', '.join(spec.prior_keys)}",
        f"  Model   : {WORKER_MODEL}",
        f"  Turns   : {spec.max_turns}",
        line=CONSOLE_SUBLINE,
    )

    started = time.monotonic()
    try:
        process = subprocess.run(
            command,
            cwd=base.ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DEFAULT_WORKER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{spec.title} exceeded the "
            f"{DEFAULT_WORKER_TIMEOUT_SECONDS}-second timeout."
        ) from exc

    duration = round(time.monotonic() - started, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"{spec.title} failed with exit code {process.returncode}.\n"
            f"{error_text}"
        )

    try:
        envelope = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{spec.title} returned invalid Claude JSON."
        ) from exc

    payload = envelope.get("structured_output")
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{spec.title} did not return structured_output."
        )

    if payload.get("domain") != spec.slug:
        raise RuntimeError(
            f"{spec.title} returned domain={payload.get('domain')!r}; "
            f"expected {spec.slug!r}."
        )

    if spec.slug != "global_pipeline":
        if payload.get("non_code_requirements"):
            raise RuntimeError(
                f"{spec.title} emitted non-code requirements owned by global_pipeline."
            )
        if payload.get("deferred_or_excluded"):
            raise RuntimeError(
                f"{spec.title} emitted deferred/excluded scope owned by global_pipeline."
            )
        if payload.get("requirement_overlays"):
            raise RuntimeError(
                f"{spec.title} emitted cross-domain overlays owned by global_pipeline."
            )

    # Prevent known-key ownership bleed.
    for item in payload.get("work_items", []):
        key = str(item.get("key", ""))
        owner = KNOWN_KEY_OWNER.get(key)
        if owner is not None and owner != spec.slug:
            raise RuntimeError(
                f"{spec.title} emitted known key {key!r}, which is routed to "
                f"{owner!r}."
            )

    print_block(
        f"[DONE]  {spec.title}",
        f"  Duration: {duration:.2f} seconds",
        line=CONSOLE_SUBLINE,
    )
    return payload


# ============================================================
# DETERMINISTIC MERGE
# ============================================================

def _append_unique_evidence(
    dest: list[dict[str, Any]],
    additions: list[dict[str, Any]],
) -> None:
    seen = {
        json.dumps(value, sort_keys=True, ensure_ascii=False)
        for value in dest
    }
    for value in additions:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if encoded not in seen:
            dest.append(value)
            seen.add(encoded)


def _append_unique_record(
    dest: list[dict[str, Any]],
    value: dict[str, Any],
) -> None:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
    for existing in dest:
        if json.dumps(existing, sort_keys=True, ensure_ascii=False) == encoded:
            return
    dest.append(value)


def merge_workers(
    results: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    work_by_key: dict[str, dict[str, Any]] = {}
    major_findings: list[str] = []
    unresolved: list[dict[str, Any]] = []
    non_code: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    overlays: list[dict[str, Any]] = []
    files_reviewed: set[str] = set()
    historical: set[str] = set()
    desired_parts: list[str] = []
    current_parts: list[str] = []
    merge_warnings: list[str] = []

    for spec in DOMAINS:
        payload = results[spec.slug]

        desired = str(payload.get("desired_state_summary", "")).strip()
        current = str(payload.get("current_state_summary", "")).strip()
        if desired:
            desired_parts.append(f"{spec.title}: {desired}")
        if current:
            current_parts.append(f"{spec.title}: {current}")

        for finding in payload.get("major_findings", []):
            finding = str(finding).strip()
            if finding and finding not in major_findings:
                major_findings.append(finding)

        for path in payload.get("files_reviewed", []):
            files_reviewed.add(str(path))
        for path in payload.get("historical_sources_reviewed", []):
            historical.add(str(path))

        for item in payload.get("work_items", []):
            key = str(item.get("key", "")).strip()
            if not key:
                raise RuntimeError(
                    f"{spec.title} returned a work item with an empty key."
                )
            if key in work_by_key:
                raise RuntimeError(
                    f"Parallel workers returned duplicate work key {key!r}. "
                    "Known domains are intentionally non-overlapping."
                )
            work_by_key[key] = item

        for item in payload.get("unresolved_questions", []):
            _append_unique_record(unresolved, item)

        for item in payload.get("non_code_requirements", []):
            _append_unique_record(non_code, item)

        for item in payload.get("deferred_or_excluded", []):
            _append_unique_record(deferred, item)

        overlays.extend(payload.get("requirement_overlays", []))

    # Apply global validation/acceptance overlays after all owners exist.
    missed_overlays: list[str] = []
    for overlay in overlays:
        owner_key = str(overlay.get("owner_key", "")).strip()
        owner = work_by_key.get(owner_key)
        if owner is None:
            missed_overlays.append(owner_key)
            continue
        _append_unique_evidence(
            owner.setdefault("acceptance_criteria", []),
            overlay.get("acceptance_criteria", []),
        )
        _append_unique_evidence(
            owner.setdefault("validation_requirements", []),
            overlay.get("validation_requirements", []),
        )

    if missed_overlays:
        merge_warnings.append(
            "Global validation overlays referenced work keys not emitted by "
            "current domain workers: " + ", ".join(sorted(set(missed_overlays)))
        )

    # Previous-output routing keys are diagnostics, not canon. Missing hinted
    # keys become review warnings only.
    expected_keys = set(KNOWN_KEY_OWNER)
    current_keys = set(work_by_key)
    missing_hints = sorted(expected_keys - current_keys)
    if missing_hints:
        merge_warnings.append(
            "Previous reconciliation routing hints not emitted by the current "
            "workers; confirm these omissions are intentional/current: "
            + ", ".join(missing_hints)
        )

    root = work_by_key.get("no-safe-circle")
    if root is None:
        raise RuntimeError(
            "global_pipeline did not emit required root key 'no-safe-circle'."
        )

    seed_status = "ready_with_warnings" if unresolved or merge_warnings else "ready"

    payload = {
        "schema_version": "1.0",
        "summary": {
            "desired_state_summary": " ".join(desired_parts),
            "current_state_summary": " ".join(current_parts),
            "major_findings": major_findings,
        },
        "sources": {
            "gdd": "Docs/GDD/No_Safe_Circle_GDD.md",
            "code_root": "Assets",
            "historical_sources_reviewed": sorted(historical),
            "files_reviewed": sorted(files_reviewed),
        },
        "work_items": list(work_by_key.values()),
        "non_code_requirements": non_code,
        "deferred_or_excluded": deferred,
        "unresolved_questions": unresolved,
        "seed_assessment": {
            "status": seed_status,
            "blockers": [],
            "warnings": merge_warnings,
        },
    }

    diagnostics = {
        "schema_version": "1.0",
        "worker_count": len(results),
        "worker_domains": [spec.slug for spec in DOMAINS],
        "previous_routing_key_count": len(expected_keys),
        "current_work_key_count": len(current_keys),
        "missing_previous_routing_hints": missing_hints,
        "missed_overlay_targets": sorted(set(missed_overlays)),
        "merge_warnings": merge_warnings,
        "overlays_applied": len(overlays) - len(missed_overlays),
        "overlays_requested": len(overlays),
    }

    return payload, diagnostics


# ============================================================
# RUNNER
# ============================================================

def run_parallel_reconciliation(
    run_paths: dict[str, Any],
) -> dict[str, Any]:
    worker_dir = run_paths["run_dir"] / "workers"
    worker_dir.mkdir(parents=True, exist_ok=False)

    print_block(
        "NO SAFE CIRCLE -- NINE-DOMAIN PARALLEL RECONCILIATION",
        f"Workers        : {len(DOMAINS)}",
        f"Parallel slots : {MAX_PARALLEL_WORKERS}",
        f"Worker model   : {WORKER_MODEL}",
        "Routing source : refined candidate 20260820T203258Z-3b04bcc8",
        "Authority      : current GDD + current repository",
    )

    started = time.monotonic()
    results: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(
        max_workers=min(MAX_PARALLEL_WORKERS, len(DOMAINS))
    ) as executor:
        futures = {
            executor.submit(_invoke_worker, spec): spec
            for spec in DOMAINS
        }

        for future in as_completed(futures):
            spec = futures[future]
            try:
                payload = future.result()
            except Exception as exc:
                raise RuntimeError(
                    f"Parallel worker failed: {spec.title}: {exc}"
                ) from exc

            results[spec.slug] = payload

            # Preserve the expensive worker immediately.
            worker_path = worker_dir / f"{spec.slug}.json"
            base.save_new_json(worker_path, payload)

    duration = round(time.monotonic() - started, 2)
    print_block(
        "WORKER PHASE COMPLETE",
        f"Completed  : {len(results)} / {len(DOMAINS)} workers",
        f"Wall clock : {duration:.2f} seconds",
    )

    payload, diagnostics = merge_workers(results)

    base.save_new_json(
        run_paths["run_dir"] / "PARALLEL_MERGE_DIAGNOSTICS.json",
        diagnostics,
    )

    # Save the deterministic pre-repair union for auditability.
    base.save_new_json(
        run_paths["run_dir"] / "PARALLEL_MERGED_CANDIDATE.raw.json",
        payload,
    )

    return payload


# ============================================================
# MAIN — REUSE EXISTING VALIDATION / OUTPUT CONTRACT
# ============================================================

def main() -> int:
    run_paths: dict[str, Any] | None = None

    try:
        run_paths = base.create_run_paths()

        payload = run_parallel_reconciliation(run_paths)

        # Keep the normal raw artifact contract too.
        base.save_new_json(run_paths["raw"], payload)

        removed_forbidden = base.sanitize_forbidden_evidence(payload)
        if removed_forbidden:
            print(
                "Warning: removed forbidden reconciliation evidence before "
                "semantic validation: "
                + ", ".join(removed_forbidden)
            )

        # Cross-domain dependencies use stable current keys. If a worker still
        # emits a dangling dependency, reuse the existing bounded repair instead
        # of repeating all nine workers.
        base.repair_missing_dependency_references(payload)

        # Same semantic validator as the original reconciliation path.
        base.run_semantic_validation(payload)

        delta = base.build_proposed_graph_delta(
            payload,
            run_id=run_paths["run_id"],
            created_at_utc=run_paths["created_at_utc"],
        )

        base.save_new_json(run_paths["json"], payload)
        base.save_new_text(run_paths["markdown"], base.render_markdown(payload))
        base.save_new_json(run_paths["delta_json"], delta)
        base.save_new_text(
            run_paths["delta_markdown"],
            base.render_graph_delta_markdown(delta),
        )

        base.write_latest_pointer(run_paths)
        base.write_current_view(
            source_reconciliation_run_id=run_paths["run_id"],
            status="unverified_reconciliation",
            candidate_json=run_paths["json"],
            candidate_markdown=run_paths["markdown"],
            delta_json=run_paths["delta_json"],
            delta_markdown=run_paths["delta_markdown"],
        )

        base.print_summary(payload, run_paths, delta)

        print()
        print(
            "Worker artifacts: "
            f"{(run_paths['run_dir'] / 'workers').relative_to(base.ROOT)}"
        )
        print(
            "Merge diagnostics: "
            f"{(run_paths['run_dir'] / 'PARALLEL_MERGE_DIAGNOSTICS.json').relative_to(base.ROOT)}"
        )
        print()
        print(
            "No full LLM closure pass was needed: domain ownership and stable "
            "routing allow deterministic merge before the existing semantic validator."
        )
        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("PARALLEL RECONCILIATION FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)

        if run_paths is not None:
            print(
                "Run directory preserved: "
                f"{run_paths['run_dir'].relative_to(base.ROOT)}",
                file=sys.stderr,
            )
            worker_dir = run_paths["run_dir"] / "workers"
            if worker_dir.exists():
                completed = sorted(
                    path.stem for path in worker_dir.glob("*.json")
                )
                if completed:
                    print(
                        "Completed workers preserved: "
                        + ", ".join(completed),
                        file=sys.stderr,
                    )

        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
