from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from output_layout import (
    LEGACY_VERIFICATIONS_DIR,
    LATEST_VERIFICATION_POINTER_PATH,
    ROOT,
    RUNS_DIR,
    load_json,
    save_json,
    verification_root,
)
from refresh_current_output import main as refresh_current


def main() -> int:
    try:
        if not LEGACY_VERIFICATIONS_DIR.exists():
            print("No legacy outputs/verifications directory exists; nothing to migrate.")
            return refresh_current()

        moved: list[dict[str, str]] = []
        for source_dir in sorted(LEGACY_VERIFICATIONS_DIR.iterdir()):
            if not source_dir.is_dir():
                continue
            source_run_id = source_dir.name
            if not (RUNS_DIR / source_run_id).exists():
                raise RuntimeError(
                    f"Legacy verification source has no reconciliation run: {source_run_id}"
                )

            target_root = verification_root(source_run_id)
            target_root.mkdir(parents=True, exist_ok=True)

            for verification_dir in sorted(source_dir.iterdir()):
                if not verification_dir.is_dir():
                    continue
                target = target_root / verification_dir.name
                if target.exists():
                    raise RuntimeError(
                        f"Refusing migration because destination already exists: {target}"
                    )
                old_rel = verification_dir.relative_to(ROOT).as_posix()
                new_rel = target.relative_to(ROOT).as_posix()
                shutil.move(str(verification_dir), str(target))
                migration = {
                    "schema_version": "1.0",
                    "change": "verification_output_layout_migration",
                    "old_directory": old_rel,
                    "new_directory": new_rel,
                    "semantic_artifacts_modified": False,
                    "note": (
                        "Directory location changed for organization only. Existing "
                        "verification artifact contents were not rewritten."
                    ),
                }
                save_json(target / "LAYOUT_MIGRATION.json", migration)
                moved.append({"old": old_rel, "new": new_rel})

            if source_dir.exists() and not any(source_dir.iterdir()):
                source_dir.rmdir()

        if LEGACY_VERIFICATIONS_DIR.exists() and not any(LEGACY_VERIFICATIONS_DIR.iterdir()):
            LEGACY_VERIFICATIONS_DIR.rmdir()

        if LATEST_VERIFICATION_POINTER_PATH.exists():
            pointer = load_json(LATEST_VERIFICATION_POINTER_PATH)
            source_run_id = str(pointer.get("source_reconciliation_run_id", ""))
            verification_run_id = str(pointer.get("latest_verification_run_id", ""))
            if source_run_id and verification_run_id:
                vdir = verification_root(source_run_id) / verification_run_id
                if vdir.exists():
                    pointer["verification_directory"] = vdir.relative_to(ROOT).as_posix()
                    pointer["verification_summary"] = (vdir / "VERIFICATION_SUMMARY.json").relative_to(ROOT).as_posix()
                    pointer["verification_markdown"] = (vdir / "VERIFICATION.md").relative_to(ROOT).as_posix()
                    save_json(LATEST_VERIFICATION_POINTER_PATH, pointer)

        print(f"Migrated {len(moved)} verification run(s) under outputs/runs/<source>/verifications/.")
        for item in moved:
            print(f"  {item['old']} -> {item['new']}")
        return refresh_current()

    except Exception as exc:
        print(f"OUTPUT LAYOUT MIGRATION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
