"""Only-copy sweep of C:\\nscrev: executables and schemas that exist nowhere in git or C:\\NSC\\tools.

Skips git repos/worktrees (reproducible from git; their untracked files are the Cleanup Agent's
worktree triage) and the two folders already preserved today.
"""
import hashlib, json, os, pathlib, re, subprocess, sys

SRC = pathlib.Path(r"C:\nscrev")
REPO = r"C:\NSC\NSC\NoSafeCircle"
TOOLS = pathlib.Path(r"C:\NSC\tools")
OUT = pathlib.Path(sys.argv[1])

CODE_EXT = {".py", ".sh", ".ps1", ".cmd", ".bat", ".psm1"}
DATA_EXT = {".json", ".yaml", ".yml", ".toml"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "Library",
             "obj", "bin", "Temp", "Logs", ".vs", "site-packages"}
ALREADY_DONE = {"ger-contract-revisions-20260916", "codex-jobs"}
MAX_BYTES = 2_000_000

print("indexing EVERY blob in the object store (not just HEAD) ...", flush=True)
# HEAD-only was wrong: a file from any older commit is recoverable from git but would
# not match HEAD, so it reported as only-copy. That produced 98,183 false positives,
# almost all of them nested repo checkouts under scratch/, review-tmp/, fixrepo-Runs/.
blobs = set()
ls = subprocess.run(["git", "-C", REPO, "cat-file", "--batch-all-objects",
                     "--batch-check=%(objectname) %(objecttype)"],
                    capture_output=True).stdout.decode(errors="replace")
for line in ls.splitlines():
    parts = line.split()
    if len(parts) == 2 and parts[1] == "blob":
        blobs.add(parts[0])
print(f"  {len(blobs)} blobs reachable in history", flush=True)

print("indexing C:\\NSC\\tools ...", flush=True)
tool_hashes = set()
for p in TOOLS.rglob("*"):
    if p.is_file():
        try:
            tool_hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
        except OSError:
            pass
print(f"  {len(tool_hashes)} files", flush=True)

SECRET_CS = re.compile(r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
                       r"|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
SECRET_CI = re.compile(r"(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]",
                       re.IGNORECASE)


def is_repo(d: pathlib.Path) -> bool:
    return (d / ".git").exists()


targets = []
for child in sorted(SRC.iterdir()):
    if child.is_file() and child.suffix.lower() in (CODE_EXT | DATA_EXT):
        targets.append(child)
    elif child.is_dir():
        if child.name in ALREADY_DONE or is_repo(child):
            continue
        try:
            if child.is_junction():
                continue
        except AttributeError:
            pass
        targets.append(child)

print(f"sweeping {len(targets)} targets ...", flush=True)

findings, scanned, skipped_big = [], 0, 0
for t in targets:
    files = [t] if t.is_file() else [
        p for p in t.rglob("*")
        if p.is_file() and not (set(p.parts) & SKIP_DIRS)
        and p.suffix.lower() in (CODE_EXT | DATA_EXT)
    ]
    for p in files:
        try:
            n = p.stat().st_size
        except OSError:
            continue
        if n > MAX_BYTES:
            skipped_big += 1
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        scanned += 1
        h = hashlib.sha256(data).hexdigest()
        if h in tool_hashes:
            continue
        # Git stores LF. These checkouts were made with core.autocrlf=true, so the working
        # -tree bytes are CRLF and never match the stored blob. Check both forms, or every
        # checked-out file on the disk reports as only-copy (it did: 97,714 of them).
        def _blob(b):
            return hashlib.sha1(b"blob " + str(len(b)).encode() + bytes([0]) + b).hexdigest()

        if _blob(data) in blobs:
            continue
        if b"\r\n" in data and _blob(data.replace(b"\r\n", b"\n")) in blobs:
            continue
        text = data.decode("utf-8", errors="replace")
        hits = [i + 1 for i, ln in enumerate(text.splitlines())
                if SECRET_CS.search(ln) or SECRET_CI.search(ln)]
        findings.append({
            "path": str(p.relative_to(SRC)),
            "top": p.relative_to(SRC).parts[0],
            "bytes": n,
            "ext": p.suffix.lower(),
            "secret_lines": hits,
        })

by_top = {}
for f in findings:
    by_top.setdefault(f["top"], []).append(f)

OUT.write_text(json.dumps({
    "scanned": scanned, "skipped_oversize": skipped_big,
    "only_copy_total": len(findings),
    "by_top": {k: v for k, v in sorted(by_top.items(), key=lambda kv: -len(kv[1]))},
}, indent=1), encoding="utf-8")

print(f"\nscanned {scanned} files, {skipped_big} skipped as oversize")
print(f"ONLY-COPY: {len(findings)} files across {len(by_top)} top-level targets\n")
for top, items in sorted(by_top.items(), key=lambda kv: -len(kv[1]))[:25]:
    code = sum(1 for i in items if i["ext"] in CODE_EXT)
    sec = sum(1 for i in items if i["secret_lines"])
    flag = f"   *** {sec} with secret-shaped lines ***" if sec else ""
    print(f"  {top:44} {len(items):4} files ({code} code){flag}")
print(f"\nfull JSON: {OUT}")
