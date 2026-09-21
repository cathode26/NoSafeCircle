"""Which executables in C:\\nscrev\\codex-jobs exist nowhere in git or C:\\NSC\\tools?"""
import hashlib, pathlib, re, subprocess

SRC = pathlib.Path(r"C:\nscrev\codex-jobs")
REPO = r"C:\NSC\NSC\NoSafeCircle"
TOOLS = pathlib.Path(r"C:\NSC\tools")
EXT = {".sh", ".py", ".ps1", ".cmd", ".bat", ".json", ".md"}

names_in_git, blobs_in_git = set(), set()
ls = subprocess.run(["git", "-C", REPO, "ls-tree", "-r", "--format=%(objectname) %(path)", "HEAD"],
                    capture_output=True).stdout.decode(errors="replace")
for line in ls.splitlines():
    oid, path = line.split(" ", 1)
    names_in_git.add(pathlib.PurePosixPath(path).name)
    blobs_in_git.add(oid)

tools_hashes = set()
for p in TOOLS.rglob("*"):
    if p.is_file():
        tools_hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())

SECRET_CS = re.compile(r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
                       r"|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
SECRET_CI = re.compile(r"(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]",
                       re.IGNORECASE)

only_copy, in_git, dup = [], [], []
for p in sorted(SRC.rglob("*")):
    if not p.is_file() or p.suffix.lower() not in EXT:
        continue
    if any(part in {".git", "__pycache__"} for part in p.parts):
        continue
    rel = p.relative_to(SRC)
    # skip generated job output: logs, prompts, per-job clones
    if len(rel.parts) > 1 and rel.parts[0] not in {"templates"}:
        continue
    data = p.read_bytes()
    h = hashlib.sha256(data).hexdigest()
    blob = subprocess.run(["git", "hash-object", "--stdin"], input=data,
                          capture_output=True).stdout.decode().strip()
    if blob in blobs_in_git:
        in_git.append(rel)
    elif h in tools_hashes:
        dup.append(rel)
    else:
        only_copy.append((rel, len(data), p))

print(f"scanned {SRC}  (top level + templates/ only; job clones and logs skipped)\n")
print(f"already in git, byte-identical : {len(in_git)}")
print(f"duplicate of C:\\NSC\\tools     : {len(dup)}")
print(f"*** ONLY COPY ***             : {len(only_copy)}\n")
for rel, n, p in only_copy:
    text = p.read_text(encoding="utf-8", errors="replace")
    hits = [i + 1 for i, ln in enumerate(text.splitlines())
            if SECRET_CS.search(ln) or SECRET_CI.search(ln)]
    flag = f"  *** SECRET-SHAPED on lines {hits} ***" if hits else "  clean"
    print(f"  {str(rel):52} {n:7} b{flag}")
