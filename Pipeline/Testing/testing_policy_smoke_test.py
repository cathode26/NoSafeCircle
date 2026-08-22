#!/usr/bin/env python3
"""Static, deterministic checks for the canonical Unity testing safeguards."""

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.is_file():
        raise AssertionError(f"Required file does not exist: {relative_path}")
    return path.read_text(encoding="utf-8-sig")


def require(text: str, pattern: str, description: str) -> None:
    if re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(description)


def main() -> int:
    policy = read("Docs/Engineering/UNITY_TESTING_POLICY.md")
    claude = read("CLAUDE.md")
    agents = read("AGENTS.md")
    start_here = read("Docs/AI-Pipeline/START_HERE.md")
    runner = read("Pipeline/Testing/run_unity_tests_clean.ps1")

    headings = (
        "Authority and scope",
        "Test classification",
        "Non-mutation invariant",
        "Scene-builder and prefab-builder rules",
        "Committed-artifact conformance tests",
        "Isolation and repeatability",
        "Contract and gate mapping",
        "Evidence claims",
        "Human runtime validation",
        "Required checklists",
        "Provider-neutral enforcement",
    )
    for heading in headings:
        require(policy, rf"^## {re.escape(heading)}\s*$", f"Policy heading missing: {heading}")

    require(policy, r"normal test execution must not modify tracked repository files", "Non-mutation rule missing")
    require(policy, r"passing assertion suite with a dirty Git tree is a failed validation run", "Passing-plus-dirty rule missing")
    require(policy, r"fresh in-memory test scene|in-memory scene-builder", "In-memory builder rule missing")
    require(policy, r"open the exact committed scene or prefab deliberately", "Committed-artifact rule missing")
    require(policy, r"builder produces this.+committed artifact currently contains this", "Builder/artifact distinction missing")

    policy_path = r"Docs/Engineering/UNITY_TESTING_POLICY\.md"
    require(claude, rf"@{policy_path}", "CLAUDE.md does not import the canonical policy")
    require(agents, policy_path, "AGENTS.md does not require the canonical policy")
    require(agents, r"must first read|must read.+first", "AGENTS.md does not require reading the policy first")
    require(start_here, rf"Unity tests.+{policy_path}", "START_HERE does not route Unity test work to the policy")

    require(runner, r"status.+--porcelain=v1.+--untracked-files=all", "Runner does not inspect tracked and untracked status")
    if len(re.findall(r"Get-WorkingTreeStatus", runner)) < 3:
        raise AssertionError("Runner does not check Git status both before and after Unity")
    require(runner, r"rev-parse.+HEAD", "Runner does not record HEAD")
    require(runner, r"rev-parse.+HEAD\^\{tree\}", "Runner does not record the Git tree")
    require(runner, r"\[System\.IO\.Path\]::GetTempPath\(\)", "Runner does not use the OS temporary directory")
    for argument in ("-batchmode", "-projectPath", "-runTests", "-testPlatform", "-testFilter", "-testResults", "-logFile"):
        require(runner, re.escape(argument), f"Unity invocation is missing {argument}")
    if re.search(r"(?im)^\s*-quit(?:\s|$)", runner):
        raise AssertionError("Runner must not invoke Unity with -quit")
    require(runner, r"unityExitCode\s*=\s*\$LASTEXITCODE", "Runner does not capture Unity's exit code")
    require(runner, r"Test-Path.+xmlPath", "Runner does not require XML output")
    require(runner, r"SelectSingleNode\(\"/test-run\"\)", "Runner does not parse the test-run element")
    require(runner, r"GetAttribute\(\$attributeName\)", "Runner does not parse numeric test-run attributes")
    require(runner, r'@\("total", "passed", "failed", "skipped"\)', "Runner does not require all result counts")
    require(runner, r"GetAttribute\(\"result\"\)", "Runner does not parse the test-run result")
    require(runner, r"failed\s+-ne\s+0", "Runner does not reject failed tests")
    require(runner, r"result\s+-ne\s+\"Passed\"", "Runner does not reject a non-Passed result")

    forbidden = r"(?im)^\s*(?:&\s*)?git(?:\.exe)?\b[^\r\n]*\b(?:restore|reset|clean)\b"
    if re.search(forbidden, runner):
        raise AssertionError("Runner contains automatic Git restore/reset/clean behavior")

    print("PASS: Unity testing policy and clean-runner safeguards are present.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
