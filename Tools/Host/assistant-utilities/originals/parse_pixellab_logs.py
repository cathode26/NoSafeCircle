from __future__ import annotations

import json
import re
import subprocess
import sys


UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def rows(name: str):
    output = subprocess.run(
        ["docker", "logs", name],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    for line in output.splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, separators=(",", ":"))


def main(names: list[str]) -> int:
    for name in names:
        uses: dict[str, dict] = {}
        print(f"=== {name} ===")
        for row in rows(name):
            if row.get("type") == "assistant":
                for item in row.get("message", {}).get("content", []):
                    tool = item.get("name", "")
                    if item.get("type") == "tool_use" and tool.startswith("mcp__pixellab__"):
                        uses[item["id"]] = {"tool": tool, "input": item.get("input", {})}
            elif row.get("type") == "user":
                for item in row.get("message", {}).get("content", []):
                    use = uses.get(str(item.get("tool_use_id", "")))
                    if item.get("type") != "tool_result" or use is None:
                        continue
                    if use["tool"] not in {
                        "mcp__pixellab__create_image_pixflux",
                        "mcp__pixellab__edit_image_pixen",
                        "mcp__pixellab__create_object_pro_fast",
                    }:
                        continue
                    value = text_of(item.get("content", ""))
                    source = str(use["input"].get("image_url", ""))
                    source_ids = UUID.findall(source)
                    record = {
                        "tool": use["tool"],
                        "seed": use["input"].get("seed"),
                        "source_id": source_ids[-1] if source_ids else None,
                        "description": use["input"].get("description"),
                        "result_ids": list(dict.fromkeys(UUID.findall(value))),
                        "error": value[:240] if "error" in value.casefold() else None,
                    }
                    print(json.dumps(record, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
