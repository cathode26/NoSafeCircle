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
        "Unity asset identity",
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
    require(policy, r"move scenes, prefabs, and other Unity assets together with their `?\.meta`? files", "Asset/meta move rule missing")
    require(policy, r"never delete or regenerate a tracked `?\.meta`? file as a relocation mechanism", "Tracked meta identity rule missing")
    require(policy, r"duplicate authoritative scenes with the same filename are prohibited", "Duplicate authoritative scene rule missing")

    policy_path = r"Docs/Engineering/UNITY_TESTING_POLICY\.md"
    require(claude, rf"@{policy_path}", "CLAUDE.md does not import the canonical policy")
    require(agents, policy_path, "AGENTS.md does not require the canonical policy")
    require(agents, r"must first read|must read.+first", "AGENTS.md does not require reading the policy first")
    require(start_here, rf"Unity tests.+{policy_path}", "START_HERE does not route Unity test work to the policy")

    require(runner, r"status.+--porcelain=v1.+--untracked-files=all", "Runner does not inspect tracked and untracked status")
    if len(re.findall(r"Get-WorkingTreeStatus", runner)) < 3:
        raise AssertionError("Runner does not check Git status both before and after Unity")
    require(runner, r"preHead\s*=.+rev-parse.+HEAD", "Runner does not record HEAD before Unity")
    require(runner, r"postHead\s*=.+rev-parse.+HEAD", "Runner does not record HEAD after Unity")
    require(runner, r"preTree\s*=.+rev-parse.+HEAD\^\{tree\}", "Runner does not record the Git tree before Unity")
    require(runner, r"postTree\s*=.+rev-parse.+HEAD\^\{tree\}", "Runner does not record the Git tree after Unity")
    require(runner, r"finally\s*\{.+postHead.+postTree.+postStatus", "Runner does not preserve post-run Git checks on failures")
    require(runner, r"\[System\.IO\.Path\]::GetTempPath\(\)", "Runner does not use the OS temporary directory")
    for argument in ("-batchmode", "-projectPath", "-runTests", "-testPlatform", "-testFilter", "-testResults", "-logFile"):
        require(runner, re.escape(argument), f"Unity invocation is missing {argument}")
    if re.search(r"(?i)(?<![\w])-quit(?![\w])", runner):
        raise AssertionError("Runner must not invoke Unity with -quit")
    require(runner, r"Start-Process.+-Wait.+-PassThru", "Runner does not explicitly wait for the Unity process")
    require(runner, r"unityExitCode\s*=\s*\$unityProcess\.ExitCode", "Runner does not capture the process object's exit code")
    if re.search(r"unityExitCode\s*=\s*\$LASTEXITCODE", runner, re.IGNORECASE):
        raise AssertionError("Runner must not use LASTEXITCODE as Unity's process exit code")
    for value in ("resolvedProjectPath", "TestFilter", "xmlPath", "logPath"):
        require(runner, rf"ConvertTo-WindowsCommandLineArgument\s+\${value}", f"Runner does not quote {value} for Unity")
    require(runner, r"xmlPublicationDeadline\s*=.+AddSeconds\(.+do\s*\{.+Test-Path.+xmlPath.+Start-Sleep.+\}\s*while", "Runner does not use bounded XML publication polling")
    stop_with_code = re.search(r"function\s+Stop-WithCode\s*\{(?P<body>.*?)^\}", runner, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    if stop_with_code is None:
        raise AssertionError("Runner does not define Stop-WithCode")
    if re.search(r"\bWrite-Error\b", stop_with_code.group("body"), re.IGNORECASE):
        raise AssertionError("Stop-WithCode must not use Write-Error")
    require(stop_with_code.group("body"), r"\[Console\]::Error\.WriteLine", "Stop-WithCode does not write failure output to stderr")
    require(runner, r"Test-Path.+xmlPath", "Runner does not require XML output")
    require(runner, r"SelectSingleNode\(\"/test-run\"\)", "Runner does not parse the test-run element")
    require(runner, r"GetAttribute\(\$attributeName\)", "Runner does not parse numeric test-run attributes")
    require(runner, r'@\("total", "passed", "failed", "skipped"\)', "Runner does not require all result counts")
    require(runner, r"GetAttribute\(\"result\"\)", "Runner does not parse the test-run result")
    require(runner, r"failed\s+-ne\s+0", "Runner does not reject failed tests")
    require(runner, r"result\s+-ne\s+\"Passed\"", "Runner does not reject a non-Passed result")

    manifest_start = runner.find('$manifestPath = Join-Path $artifactDirectory "validation-manifest.json"')
    final_success = runner.find('Write-Host "VALIDATION PASSED:')
    failed_check = runner.find('if ($failed -ne 0)')
    passed_check = runner.find('if ($result -ne "Passed")')
    if not (failed_check < passed_check < manifest_start < final_success):
        raise AssertionError("Runner does not publish the manifest only after all result success checks")
    for fact in ("preHead", "preTree", "postHead", "postTree", "TestPlatform", "TestFilter",
                 "result", "total", "passed", "failed", "skipped", "xmlHash", "logHash"):
        require(runner[manifest_start:final_success], rf"\${fact}\b", f"Manifest does not include deterministic fact {fact}")
    require(runner, r"Get-FileHash.+xmlPath.+SHA256", "Runner does not hash the XML artifact")
    require(runner, r"Get-FileHash.+logPath.+SHA256", "Runner does not hash the log artifact")
    require(runner, r"UTF8Encoding\(\$false\)", "Runner does not explicitly write UTF-8 without BOM")
    require(runner, r"manifestTemporaryPath.+Guid.+FileStream.+Flush\(\$true\).+File\]::Move\(\$manifestTemporaryPath, \$manifestPath\)",
            "Runner does not atomically publish a flushed unique temporary manifest")
    require(runner, r'Write-Host "Validation manifest: \$manifestPath"', "Runner does not print the validation manifest path")

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
