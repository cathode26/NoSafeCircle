"""Apply a GER re-audit's quoted replacement text verbatim to the round-03 final contract.

Usage:
    python ger_patch.py --packet <packet-dir> --replacements <replacements.json>

The GER owner authors no contract wording here. Every replacement text must be quoted in the
round-04 re-audit (whitespace and markdown quote markers ignored), and every anchor must occur
exactly once in its target field. The tool writes an immutable 05-owner-patch round directory:
PATCHED_CONTRACT.json, PATCH_LOG.json, OUTPUT.md (patch table plus the patched contract) and
METADATA.json. A fresh Claude re-check (06-claude-recheck) must then approve it before
apply_contract.py will commit it. Never edits the repository.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re

ROUND = "05-owner-patch"
ID_KEYS = {"acceptance_criteria": "criterion_id", "completion_gates": "gate_id",
           "downstream_integration_obligations": "obligation_id"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize(text: str) -> str:
    text = re.sub(r"(?m)^\s*>\s?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def final_contract(text: str) -> dict:
    start = text.lower().find("final proposed task contract")
    if start < 0:
        raise ValueError("round 03 output has no 'Final proposed task contract' section")
    match = re.search(r"```json\s*(.*?)```", text[start:], flags=re.S)
    if not match:
        raise ValueError("round 03 final contract section has no ```json block")
    return json.loads(match.group(1))


def resolve(contract: dict, target: str) -> tuple[dict, str]:
    parts = target.split(":")
    if len(parts) == 1:
        if parts[0] not in contract or not isinstance(contract[parts[0]], str):
            raise ValueError(f"target {target} is not a top-level string field")
        return contract, parts[0]
    if len(parts) != 3 or parts[0] not in ID_KEYS:
        raise ValueError(f"unsupported target {target}")
    collection, item_id, field = parts
    matches = [item for item in contract.get(collection, []) if item.get(ID_KEYS[collection]) == item_id]
    if len(matches) != 1 or not isinstance(matches[0].get(field), str):
        raise ValueError(f"target {target} matched {len(matches)} items or is not a string field")
    return matches[0], field


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--packet", required=True, type=pathlib.Path)
    parser.add_argument("--replacements", required=True, type=pathlib.Path)
    args = parser.parse_args()
    packet = args.packet.resolve()
    round_dir = packet / ROUND
    round_dir.mkdir()  # immutable: fails if the round already exists
    try:
        identity = json.loads((packet / "SOURCE_IDENTITY.json").read_text(encoding="utf-8"))
        refine_bytes = (packet / "03-codex-refine" / "OUTPUT.md").read_bytes()
        reaudit_bytes = (packet / "04-claude-reaudit" / "OUTPUT.md").read_bytes()
        spec_bytes = args.replacements.read_bytes()
        spec = json.loads(spec_bytes)
        if spec.get("task_id") != identity["task_id"] or spec.get("packet") != packet.name:
            raise ValueError(f"replacements are for {spec.get('task_id')} / {spec.get('packet')}, not {identity['task_id']} / {packet.name}")
        contract = final_contract(refine_bytes.decode("utf-8"))
        reaudit = normalize(reaudit_bytes.decode("utf-8"))
        log = []
        for item in spec["replacements"]:
            if item["op"] == "insert_list_after":
                # Insert quoted items into a top-level list (for example exclusive_resources) after one anchor item.
                values = contract.get(item["target"])
                if not isinstance(values, list) or values.count(item["old"]) != 1:
                    raise ValueError(f"{item['id']}: anchor item must occur exactly once in list {item['target']}")
                new_items = [value.strip() if isinstance(value, str) else value for value in item["new_items"]]
                for value in new_items:
                    if isinstance(value, dict):
                        # An object item (for example a gdd_evidence entry) must carry the anchor item's keys,
                        # and every one of its string values must be quoted in the re-audit.
                        if not isinstance(item["old"], dict) or set(value) != set(item["old"]):
                            raise ValueError(f"{item['id']}: object list item keys differ from the anchor item's keys")
                        texts = list(value.values())
                    else:
                        texts = [value]
                    if not all(isinstance(text, str) and normalize(text) in reaudit for text in texts):
                        raise ValueError(f"{item['id']}: list item is not quoted in the round-04 re-audit: {value}")
                    if value in values:
                        raise ValueError(f"{item['id']}: list item already present: {value}")
                before_list = json.dumps(values, ensure_ascii=False)
                index = values.index(item["old"]) + 1
                contract[item["target"]] = values[:index] + new_items + values[index:]
                log.append({"id": item["id"], "target": item["target"], "op": item["op"], "old": item["old"],
                            "new": new_items, "field_sha256_before": sha256(before_list.encode("utf-8")),
                            "field_sha256_after": sha256(json.dumps(contract[item["target"]], ensure_ascii=False).encode("utf-8"))})
                continue
            holder, field = resolve(contract, item["target"])
            before = holder[field]
            new = item["new"].strip()
            if normalize(new) not in reaudit:
                raise ValueError(f"{item['id']}: replacement text is not quoted in the round-04 re-audit")
            if item["op"] in ("replace", "insert_after", "insert_after_tight"):
                count = before.count(item["old"])
                if count != 1:
                    raise ValueError(f"{item['id']}: anchor occurs {count} times in {item['target']}, expected 1")
                if item["op"] == "replace":
                    replacement = new
                elif item["op"] == "insert_after":
                    replacement = item["old"] + " " + new
                else:
                    # The quoted insertion begins with punctuation, so it joins the anchor without a space.
                    if not new or new[0] not in ",;:.)":
                        raise ValueError(f"{item['id']}: insert_after_tight text must start with punctuation")
                    replacement = item["old"] + new
                after = before.replace(item["old"], replacement)
            elif item["op"] == "append":
                after = before.rstrip() + " " + new
            elif item["op"] == "set":
                # Whole-field replacement quoted by the re-audit; the expected current value must match exactly.
                if item.get("old") is None or before != item["old"]:
                    raise ValueError(f"{item['id']}: current value of {item['target']} differs from the expected old value")
                after = new
            else:
                raise ValueError(f"{item['id']}: unsupported op {item['op']}")
            holder[field] = after
            log.append({"id": item["id"], "target": item["target"], "op": item["op"], "old": item.get("old"),
                        "new": new, "field_sha256_before": sha256(before.encode("utf-8")),
                        "field_sha256_after": sha256(after.encode("utf-8"))})
        patched = (json.dumps(contract, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        (round_dir / "PATCHED_CONTRACT.json").write_bytes(patched)
        (round_dir / "PATCH_LOG.json").write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        rows = "\n".join(f"| {entry['id']} | `{entry['target']}` | {entry['op']} |" for entry in log)
        output = (f"# {identity['task_id']} owner patch: round-04 replacements applied verbatim\n\n"
                  f"The GER owner applied only the replacement text quoted in 04-claude-reaudit/OUTPUT.md "
                  f"(sha256 {sha256(reaudit_bytes)}) to the round-03 final contract (03-codex-refine/OUTPUT.md "
                  f"sha256 {sha256(refine_bytes)}). No other wording was authored. Each anchor matched exactly once.\n\n"
                  f"| Replacement | Target field | Operation |\n|---|---|---|\n{rows}\n\n"
                  "## Replacement log\n\n```json\n" + json.dumps(log, indent=2, ensure_ascii=False) + "\n```\n\n"
                  "## Patched task contract\n\n```json\n" + patched.decode("utf-8") + "```\n")
        (round_dir / "OUTPUT.md").write_text(output, encoding="utf-8")
        metadata = {"round": ROUND, "task_id": identity["task_id"], "tool": "ger_patch.py",
                    "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "packet_source_head": identity["source_head"], "replacements_file": str(args.replacements.resolve()),
                    "input_sha256": {"03-codex-refine/OUTPUT.md": sha256(refine_bytes),
                                     "04-claude-reaudit/OUTPUT.md": sha256(reaudit_bytes),
                                     "replacements": sha256(spec_bytes)},
                    "replacement_count": len(log), "patched_contract_sha256": sha256(patched),
                    "output_sha256": sha256((round_dir / "OUTPUT.md").read_bytes())}
        (round_dir / "METADATA.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    except (ValueError, KeyError, OSError) as error:
        (round_dir / "FAILED.json").write_text(json.dumps({"failed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                                          "reason": str(error)}, indent=2) + "\n", encoding="utf-8")
        print(f"GER PATCH FAILED: {error}")
        return 2
    print(json.dumps({"round": ROUND, "task_id": identity["task_id"], "replacements": len(log),
                      "patched_contract_sha256": metadata["patched_contract_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
