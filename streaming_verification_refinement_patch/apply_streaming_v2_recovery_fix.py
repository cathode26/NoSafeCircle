from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Pipeline" / "Reconciliation" / "streaming_refinement_v2.py"
MARKER = "recovered_failures"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Streaming v2 recovery bookkeeping fix is already installed.")
        return 0

    text = replace_once(
        text,
        "        base.save_new_json(self.conflict_path, self.conflict_report)\n",
        "        # This report is derived while the verification run is still in progress;\n"
        "        # a failed local repair may be recovered before synthesis, so refresh it.\n"
        "        base.save_json(self.conflict_path, self.conflict_report)\n",
        "refreshable conflict report",
    )

    old_recovery = '''        if self.failures:
            self.failures.clear()
            self._build_conflict_report()
'''
    new_recovery = '''        if self.failures:
            recovered_failures = sorted(self.failures)
            self.failures.clear()
            self._build_conflict_report()
            manifest = base.load_json(self.manifest_path)
            manifest["repairs"] = [
                {
                    "audit_key": key,
                    "requested_model": envelope.get("requested_model"),
                    "duration_seconds": envelope.get("duration_seconds"),
                    "repair": envelope.get("result"),
                }
                for key, envelope in sorted(self.repairs.items())
            ]
            manifest["failures"] = {}
            manifest["recovered_failures"] = recovered_failures
            manifest["deterministic_conflict_report"] = self.conflict_report
            base.save_json(self.manifest_path, manifest)
'''
    text = replace_once(text, old_recovery, new_recovery, "recovery manifest refresh")

    TARGET.write_text(text, encoding="utf-8")
    print("Fixed streaming v2 recovery conflict/manifest bookkeeping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
