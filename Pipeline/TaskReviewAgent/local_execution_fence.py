"""Explicit host command and provider network boundary for local rehearsals.

Production callers never install this policy. A local host process installs a
command audit policy covering its Python process-creation APIs. This protects
the trusted host pipeline; it is not a sandbox for arbitrary in-process Python.
Provider containers have an internal-only network;
their only egress is the separately trusted, provider-host-only TLS gateway.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sys
import subprocess
from typing import Any, Sequence


class LocalPublicationRefused(RuntimeError):
    """An operation is outside the local rehearsal authority."""


_CONTEXT: Any = None
_PREPARED_DOCKER_COMMANDS: set[tuple[str, ...]] = set()
_PREPARED_CLEANUP_COMMANDS: set[tuple[str, tuple[str, ...]]] = set()
_AUTHENTICATION_VOLUMES: dict[str, str] = {}
# Review-only decomposition is a provider boundary a local run may reach, so
# its services are named here exactly as the implementation roles are. The
# cross-provider D1B.2 container is not provider-scoped and carries its own
# name, matching the committed production Compose definition.
_SERVICES = frozenset(
    {f"{provider}-{role}" for provider in ("claude", "codex")
     for role in ("review", "exec", "supervisor", "decompose")}
    | {"round-robin-decompose"}
)
_GIT_READ = frozenset({"rev-parse", "status", "show", "cat-file", "ls-files", "ls-tree",
                       "diff", "diff-tree", "log", "merge-base", "check-ignore",
                       "check-attr", "for-each-ref", "show-ref", "symbolic-ref", "version"})
_GIT_LOCAL = frozenset({"clone", "switch", "checkout", "add", "commit", "apply", "config",
                        "init", "branch", "remote", "hash-object", "update-index"})
# The exact Stage D1C boundary (``apply_graph_delta``) needs these on the
# run-owned source, and only while ``local_decomposition_apply_scope`` is open
# for one explicitly authorized application: history inspection, staging, the
# single canonical commit, and its own restore/rollback of that source.
_GIT_APPLY_SCOPE_READ = frozenset({"rev-list"})
_GIT_APPLY_SCOPE_LOCAL = frozenset({"add", "commit", "reset", "restore"})
_LOCAL_DECOMPOSITION_APPLY_SCOPE: tuple[str, Path] | None = None
_LOCAL_CANDIDATE_SCOPE: tuple[str, Path, Path, Path | None] | None = None
_LOCAL_CANDIDATE_CLONES: set[Path] = set()


def _root(context: Any) -> Path:
    return Path(context.run_root).resolve()


def _authentication_volume(provider: str) -> str:
    """The external credential store a seed job reads, captured before
    ``configure_local_process`` repointed the variable at this run's own store."""
    return (_AUTHENTICATION_VOLUMES.get(provider)
            or os.environ.get(f"NSC_TASK_SUPERVISOR_{provider.upper()}_VOLUME")
            or f"nosafecircle_{provider}-config")


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def refuse_production_operation(operation: str, context: Any = None) -> None:
    if context is not None or _CONTEXT is not None:
        raise LocalPublicationRefused(f"LOCAL REHEARSAL forbids {operation}")


@contextmanager
def local_decomposition_apply_scope(context: Any, *, source_root: str | Path):
    """Admit the exact D1C boundary on this run's own source for one application.

    Opened only by the local decomposition continuation, immediately around
    ``apply_graph_delta`` and its interrupted-application recovery, for a run
    that recorded the explicit ``local_decomposition_apply`` setting. Outside
    the scope the source stays as read-only to this process as before; inside
    it, only the run's exact source checkout gains the four extra operations.
    """
    global _LOCAL_DECOMPOSITION_APPLY_SCOPE
    if not getattr(context, "local_decomposition_apply", False):
        raise LocalPublicationRefused("local decomposition application requires the run's explicit setting")
    root = Path(source_root).resolve()
    if root != Path(context.source_root).resolve():
        raise LocalPublicationRefused("local decomposition application is limited to the run's own source")
    if _inside(root, _root(context)) or _inside(_root(context), root):
        raise LocalPublicationRefused("local decomposition application requires a source disjoint from the run root")
    if _LOCAL_DECOMPOSITION_APPLY_SCOPE is not None:
        raise LocalPublicationRefused("one local decomposition application at a time")
    _LOCAL_DECOMPOSITION_APPLY_SCOPE = (project_name(context), root)
    try:
        yield
    finally:
        _LOCAL_DECOMPOSITION_APPLY_SCOPE = None


def _in_apply_scope(context: Any, repository: Path) -> bool:
    scope = _LOCAL_DECOMPOSITION_APPLY_SCOPE
    return scope is not None and scope == (project_name(context), repository)


@contextmanager
def local_candidate_integration_scope(context: Any, *, checkout: str | Path,
                                      scratch_root: str | Path | None = None):
    """Admit only verified local candidate Git work for one run and checkout."""
    global _LOCAL_CANDIDATE_SCOPE
    _LOCAL_CANDIDATE_CLONES.clear()
    if not getattr(context, "local_candidate_auto_accept", False):
        raise LocalPublicationRefused("local candidate integration requires the run's explicit setting")
    source = Path(context.source_root).resolve()
    candidate_checkout = Path(checkout).resolve()
    if not _inside(candidate_checkout, _root(context)) or source == candidate_checkout:
        raise LocalPublicationRefused("local candidate authority requires its run-owned checkout")
    if _LOCAL_CANDIDATE_SCOPE is not None:
        raise LocalPublicationRefused("one local candidate integration at a time")
    scratch = Path(scratch_root).resolve() if scratch_root is not None else None
    if scratch is not None and not _inside(scratch, _root(context)):
        raise LocalPublicationRefused("local candidate validation scratch must belong to its run")
    _LOCAL_CANDIDATE_SCOPE = (project_name(context), source, candidate_checkout, scratch)
    try:
        yield
    finally:
        _LOCAL_CANDIDATE_CLONES.clear()
        _LOCAL_CANDIDATE_SCOPE = None


def register_local_candidate_clone(context: Any, clone: str | Path) -> None:
    scope = _LOCAL_CANDIDATE_SCOPE
    path = Path(clone).resolve()
    if (scope is None or scope[0] != project_name(context) or scope[3] is None
            or not _inside(path, scope[3])):
        raise LocalPublicationRefused("local candidate clone is outside its authenticated scratch root")
    _LOCAL_CANDIDATE_CLONES.add(path)


def _in_candidate_scope(context: Any, repository: Path) -> bool:
    scope = _LOCAL_CANDIDATE_SCOPE
    return (scope is not None and scope[0] == project_name(context)
            and (repository in {scope[1], scope[2]} or repository in _LOCAL_CANDIDATE_CLONES))


def _empty_hooks_directory(value: str) -> bool:
    if value in {"", "/dev/null", "NUL"}:
        return True
    if _LOCAL_DECOMPOSITION_APPLY_SCOPE is None:
        return False
    # D1C neutralizes hooks with a fresh empty directory; only an existing
    # directory that contains nothing at all is equivalent to "no hooks".
    directory = Path(value)
    try:
        return directory.is_dir() and not any(directory.iterdir())
    except OSError:
        return False


def validate_local_command(command: Sequence[str], context: Any, *, cwd: str | Path | None = None) -> None:
    """Reject publication and unbounded wrappers before starting a host process."""
    if isinstance(command, (str, bytes)) or not command:
        raise LocalPublicationRefused("LOCAL REHEARSAL requires explicit argv, never a shell string")
    argv = tuple(os.fsdecode(arg) for arg in command)
    name = Path(argv[0]).name.lower().removesuffix(".exe")
    if name == "gh":
        raise LocalPublicationRefused("LOCAL REHEARSAL has no GitHub command authority")
    if name == "git":
        index = 1
        repository = Path(cwd or os.getcwd()).resolve()
        while index < len(argv) and argv[index].startswith("-"):
            option = argv[index]
            if option == "-C" and index + 1 < len(argv):
                repository = (repository / argv[index + 1]).resolve()
                index += 2
            elif option in {"--no-optional-locks", "--no-pager"}:
                index += 1
            elif option == "-c" and index + 1 < len(argv):
                key = argv[index + 1].partition("=")[0].casefold()
                if key not in {"core.longpaths", "core.autocrlf", "core.filemode", "core.hookspath",
                               "user.name", "user.email", "commit.gpgsign"}:
                    raise LocalPublicationRefused(f"LOCAL REHEARSAL forbids Git override {key}")
                if key == "core.hookspath" and not _empty_hooks_directory(argv[index + 1].partition("=")[2]):
                    raise LocalPublicationRefused("LOCAL REHEARSAL forbids executable Git hooks")
                index += 2
            else:
                raise LocalPublicationRefused(f"LOCAL REHEARSAL forbids Git option {option}")
        if index == len(argv):
            raise LocalPublicationRefused("LOCAL REHEARSAL requires an explicit Git operation")
        operation, arguments = argv[index], argv[index + 1:]
        apply_scoped = _in_apply_scope(context, repository)
        candidate_scoped = _in_candidate_scope(context, repository)
        if apply_scoped and operation in _GIT_APPLY_SCOPE_READ:
            return
        if apply_scoped and operation in _GIT_APPLY_SCOPE_LOCAL:
            return
        if candidate_scoped and operation in {"reset", "restore", "clean", "write-tree"}:
            return
        if candidate_scoped and repository == _LOCAL_CANDIDATE_SCOPE[1] and operation in {
                "apply", "add", "commit"}:
            return
        if apply_scoped and operation == "hash-object" and "-w" not in arguments:
            # D1C compares materialized bytes with committed blobs through
            # `git hash-object --stdin --path`; without -w nothing is written.
            return
        if operation not in _GIT_READ | _GIT_LOCAL:
            raise LocalPublicationRefused(f"LOCAL REHEARSAL forbids git {operation}")
        if operation in _GIT_READ:
            if any(arg in {"--ext-diff", "--textconv"} or arg.startswith("--output") for arg in arguments):
                raise LocalPublicationRefused("LOCAL REHEARSAL forbids external Git filters")
            if operation == "symbolic-ref" and (
                    any(arg not in {"--quiet", "--short", "HEAD"} for arg in arguments)
                    or arguments.count("HEAD") != 1):
                raise LocalPublicationRefused("LOCAL REHEARSAL allows only reading symbolic HEAD")
            return
        if operation == "clone":
            paths = []
            clone_index = 0
            while clone_index < len(arguments):
                argument = arguments[clone_index]
                if argument == "--origin" and clone_index + 1 < len(arguments):
                    clone_index += 2
                    continue
                if argument in {"--local", "--no-local", "--no-hardlinks", "--no-checkout", "--"}:
                    clone_index += 1
                    continue
                if argument.startswith("-"):
                    raise LocalPublicationRefused("LOCAL REHEARSAL forbids this clone option")
                paths.append(argument)
                clone_index += 1
            if (len(paths) != 2 or not (repository / paths[0]).is_dir()
                    or not _inside((repository / paths[1]).resolve(), _root(context))):
                raise LocalPublicationRefused("LOCAL REHEARSAL clones only local Git objects into its own run root")
            return
        if operation == "config":
            config_flags = {"--get", "--get-all", "--get-regexp", "--list", "--show-origin",
                            "--local", "--null", "-z", "--replace-all"}
            if any(arg.startswith("-") and arg not in config_flags for arg in arguments):
                raise LocalPublicationRefused("LOCAL REHEARSAL forbids external Git configuration options")
            actions = [arg for arg in arguments if arg in
                       {"--get", "--get-all", "--get-regexp", "--list", "--replace-all"}]
            if len(actions) > 1:
                raise LocalPublicationRefused("LOCAL REHEARSAL forbids ambiguous Git configuration actions")
            keys = [arg for arg in arguments if not arg.startswith("-")]
            if (actions and actions[0] != "--replace-all") or (not actions and len(keys) == 1):
                return
        if operation == "remote" and (not arguments or arguments[0] in {"get-url", "-v"}):
            return
        if operation == "branch" and arguments in {( "--show-current",), ("--list",)}:
            return
        if not _inside(repository, _root(context)):
            raise LocalPublicationRefused("LOCAL REHEARSAL may mutate only its own task checkouts")
        if operation == "apply":
            # Redirecting output, overriding Git's path protections or writing
            # a fake index would defeat the cwd boundary. Admit only the patch
            # operations the local host needs, with inputs inside its namespace.
            flags = {"--check", "--index", "--cached", "--3way", "--reverse", "-R",
                     "--recount", "--stat", "--numstat", "--summary", "--binary",
                     "--whitespace=nowarn", "--whitespace=warn", "--whitespace=error",
                     "--whitespace=error-all", "--whitespace=fix"}
            positional = False
            for argument in arguments:
                if not positional and argument == "--":
                    positional = True
                elif not positional and argument in flags:
                    continue
                elif (not positional and argument.startswith("-")) or not _inside(
                        (repository / argument).resolve(), _root(context)):
                    raise LocalPublicationRefused("LOCAL REHEARSAL forbids unsafe Git patch flags or paths")
        if operation == "init":
            positional = False
            for argument in arguments:
                if not positional and argument == "--":
                    positional = True
                elif not positional and argument in {"--quiet", "-q"}:
                    continue
                elif (not positional and argument.startswith("-")) or not _inside(
                        (repository / argument).resolve(), _root(context)):
                    raise LocalPublicationRefused("LOCAL REHEARSAL forbids Git templates or external initialization paths")
        if operation == "config":
            if any(arg in {"--global", "--system", "--file", "-f"} for arg in arguments):
                raise LocalPublicationRefused("LOCAL REHEARSAL forbids external Git configuration")
            keys = [arg for arg in arguments if not arg.startswith("-")]
            if not keys or keys[0].casefold() not in {"user.name", "user.email", "core.longpaths", "core.autocrlf",
                                                        "core.filemode", "core.hookspath", "commit.gpgsign",
                                                        "remote.origin.url", "remote.origin.pushurl"}:
                raise LocalPublicationRefused("LOCAL REHEARSAL forbids this Git configuration mutation")
            if keys[0].casefold() == "core.hookspath" and (len(keys) != 2 or keys[1] not in {"", "/dev/null", "NUL"}):
                raise LocalPublicationRefused("LOCAL REHEARSAL forbids executable Git hooks")
        if operation == "remote" and (not arguments or arguments[0] not in {"add", "set-url", "remove"}):
            raise LocalPublicationRefused("LOCAL REHEARSAL forbids remote ref operations")
        if operation == "remote" and any(arg.startswith("-") for arg in arguments[1:]):
            raise LocalPublicationRefused("LOCAL REHEARSAL forbids remote options that can fetch or mirror refs")
        if operation in {"switch", "checkout", "branch"} and any(arg.startswith("refs/remotes/") for arg in arguments):
            raise LocalPublicationRefused("LOCAL REHEARSAL forbids remote ref changes")
        return
    if name == "docker":
        if not context.allow_live_canary:
            raise LocalPublicationRefused("Docker provider calls require explicit -AllowLiveCanary")
        if (project_name(context), argv) in _PREPARED_CLEANUP_COMMANDS:
            return
        expected_file = str(_root(context) / "provider-runtime" / "compose.json")
        expected_project = project_name(context)
        if len(argv) < 7 or argv[1:6] != ("compose", "-f", expected_file, "-p", expected_project):
            raise LocalPublicationRefused("LOCAL REHEARSAL permits only its isolated provider Compose project")
        if argv[6] not in {"run", "up", "stop", "config", "build", "ps"}:
            raise LocalPublicationRefused("LOCAL REHEARSAL forbids this Docker lifecycle command")
        if argv not in _PREPARED_DOCKER_COMMANDS:
            raise LocalPublicationRefused("LOCAL REHEARSAL refuses unprepared Docker flags or services")
        return
    if name in {"python", "python3", "python3.11", "python3.12", "python3.13"}:
        if (len(argv) < 2 or argv[1].startswith("-") or not argv[1].endswith(".py")
                or any(re.match(r"^-[A-Za-z]*[cm]", arg) for arg in argv[1:])):
            raise LocalPublicationRefused("LOCAL REHEARSAL refuses unbounded Python commands")
        source_root = getattr(context, "source_root", None)
        if source_root is None:
            raise LocalPublicationRefused("LOCAL REHEARSAL requires exact source identity for child Python")
        script = (Path(cwd or os.getcwd()) / argv[1]).resolve()
        source_root = Path(source_root).resolve()
        allowed = {source_root / "Pipeline/TaskReviewAgent" / entry for entry in
                   ("run_pipeline_agent.py", "run_autonomous_graph.py", "host_worker_launcher.py",
                    # Review-only decomposition is the second worker boundary a
                    # local scheduler may dispatch. It is admitted on the same
                    # terms as the implementation worker: the clause below still
                    # requires its argv to name this exact run root.
                    "host_decomposition_launcher.py")}
        taskcontrol = source_root / "Pipeline/TaskGraph/taskcontrol.py"
        candidate_taskcontrol = (_LOCAL_CANDIDATE_SCOPE is not None
            and any(script == root / "Pipeline/TaskGraph/taskcontrol.py"
                    for root in {_LOCAL_CANDIDATE_SCOPE[2], *_LOCAL_CANDIDATE_CLONES}))
        if script == taskcontrol:
            arguments = argv[2:]
            if not arguments or arguments[0] not in {"validate", "show", "state", "states"}:
                raise LocalPublicationRefused("LOCAL REHEARSAL allows only read-only TaskGraph commands")
            return
        if candidate_taskcontrol:
            arguments = argv[2:]
            if arguments != ("validate",):
                raise LocalPublicationRefused(
                    "local candidate scope allows only TaskGraph validation")
            return
        if script not in allowed:
            raise LocalPublicationRefused("LOCAL REHEARSAL refuses delivery or unapproved Python entry points")
        if script.name == "run_autonomous_graph.py":
            if "--local-rehearsal" not in argv:
                raise LocalPublicationRefused("local controller child must preserve explicit mode")
        elif "--local-rehearsal-run-root" not in argv or (
                Path(argv[argv.index("--local-rehearsal-run-root") + 1]).resolve() != _root(context)):
            raise LocalPublicationRefused("local worker child must preserve the exact run namespace")
        return
    if name in {"powershell", "pwsh"}:
        if len(argv) < 6 or argv[1:5] != ("-NoProfile", "-ExecutionPolicy", "Bypass", "-File"):
            raise LocalPublicationRefused("LOCAL REHEARSAL refuses unbounded PowerShell")
        script = Path(argv[5])
        source_root = getattr(context, "source_root", None)
        expected = Path(source_root) / "Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1" if source_root else None
        if (expected is None or script.resolve() != expected.resolve() or "-LocalRehearsal" not in argv
                or "-LocalRehearsalRunRoot" not in argv
                or Path(argv[argv.index("-LocalRehearsalRunRoot") + 1]).resolve() != _root(context)):
            raise LocalPublicationRefused("LOCAL REHEARSAL workers require the canonical local launcher")
        return
    raise LocalPublicationRefused(f"LOCAL REHEARSAL refuses executable {name}")


def configure_local_process(context: Any) -> None:
    """Install once at the explicit local CLI boundary; never infer a backend."""
    global _CONTEXT
    if _CONTEXT is not None:
        if _root(_CONTEXT) != _root(context):
            raise LocalPublicationRefused("a host process cannot change its local run namespace")
        return
    _CONTEXT = context
    for provider in ("claude", "codex"):
        variable = f"NSC_TASK_SUPERVISOR_{provider.upper()}_VOLUME"
        _AUTHENTICATION_VOLUMES[provider] = os.environ.get(variable) or f"nosafecircle_{provider}-config"
        os.environ[variable] = f"{project_name(context)}_{provider}-config"
    os.environ["NSC_TASK_AGENT_COMPOSE_PROJECT"] = project_name(context)
    os.environ["PYTHONUNBUFFERED"] = "1"

    # Bind the selected validator and decoder now, so rebinding the public
    # module attribute cannot silently repoint an installed policy.
    validate = validate_local_command
    decode_windows = _windows_argv
    windows = os.name == "nt"
    execute_child_code = subprocess.Popen._execute_child.__code__
    current_frame = sys._getframe

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event in {"subprocess.Popen", "_winapi.CreateProcess"}:
            if event == "subprocess.Popen":
                executable, argv, cwd, _ = args
            else:
                # Some Windows CPython builds emit an unusable command-line
                # value in this native audit event. Admit only the canonical
                # subprocess call frame, and validate its actual arguments.
                # A direct _winapi call has no such frame and is always refused.
                frame = current_frame(1)
                if frame.f_code is not execute_child_code:
                    raise LocalPublicationRefused("LOCAL REHEARSAL refuses direct Windows process creation")
                executable = frame.f_locals["executable"]
                argv = frame.f_locals["args"]
                cwd = frame.f_locals["cwd"]
            if windows and isinstance(argv, str):
                argv = decode_windows(argv)
            if executable is not None and (Path(os.fsdecode(executable)).name.lower().removesuffix(".exe")
                                          != Path(argv[0]).name.lower().removesuffix(".exe")):
                raise LocalPublicationRefused("LOCAL REHEARSAL refuses executable substitution")
            validate(argv, context, cwd=cwd)
        elif (event in {"os.system", "os.fork", "os.forkpty", "os.startfile", "os.startfile/2"}
              or event.startswith(("os.spawn", "os.posix_spawn", "os.exec", "_winapi.CreateProcess"))):
            raise LocalPublicationRefused("LOCAL REHEARSAL refuses shell/spawn bypasses")
    sys.addaudithook(audit)


def _windows_argv(command_line: str) -> tuple[str, ...]:
    # CPython's Windows audit event occurs after list2cmdline. Decode using
    # Windows itself, then require the canonical round trip; never split on
    # whitespace or let quoting hide a publication command.
    import ctypes
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command_line, ctypes.byref(count))
    if not pointer:
        raise LocalPublicationRefused("LOCAL REHEARSAL cannot parse the Windows command line")
    try:
        argv = tuple(pointer[index] for index in range(count.value))
    finally:
        kernel.LocalFree(pointer)
    if subprocess.list2cmdline(argv) != command_line:
        raise LocalPublicationRefused("LOCAL REHEARSAL requires canonical Windows argv quoting")
    return argv


def project_name(context: Any) -> str:
    return "nsc-local-" + hashlib.sha256(str(_root(context)).encode()).hexdigest()[:20]


def current_local_context() -> Any:
    """Return only the context installed by an explicit local CLI boundary."""
    return _CONTEXT


def _credential_seed_script(provider: str) -> str:
    """Seed structurally valid JSON without adopting other provider-store files."""
    name = ".credentials.json" if provider == "claude" else "auth.json"
    return "\n".join((
        "from pathlib import Path",
        "import json, os, pwd",
        f"source = Path('/authentication') / {name!r}",
        "directory = Path('/sessions')",
        f"target = directory / {name!r}",
        "if source.is_symlink() or target.is_symlink():",
        "    raise SystemExit('provider authentication symlinks are refused')",
        "def invalid_json_constant(value):",
        "    raise ValueError('nonstandard JSON constant')",
        "def authentication_bytes(path):",
        "    if not path.is_file():",
        "        raise SystemExit('provider authentication must be a regular file')",
        "    try:",
        "        payload = path.read_bytes()",
        "        value = json.loads(payload.decode('utf-8'), parse_constant=invalid_json_constant)",
        "        if not payload or not isinstance(value, dict):",
        "            raise ValueError()",
        "    except (OSError, UnicodeError, ValueError):",
        "        raise SystemExit('provider authentication must contain a UTF-8 JSON object') from None",
        "    return payload",
        "payload = authentication_bytes(source) if source.exists() else None",
        "if target.exists():",
        "    authentication_bytes(target)",
        "else:",
        "    if payload is None:",
        "        raise SystemExit('provider authentication file is missing')",
        "    with target.open('xb') as stream:",
        "        stream.write(payload)",
        "account = pwd.getpwnam('agent')",
        "for path in (directory, target):",
        "    os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)",
    ))


def _provider_executable_check_script(provider: str) -> str:
    """Check installation and Codex image ownership without running a provider."""
    return "\n".join((
        "from pathlib import Path",
        "import os, shutil, stat",
        f"candidate = shutil.which({provider!r})",
        "if not candidate:",
        "    raise SystemExit('provider executable is missing')",
        "executable = Path(candidate).resolve(strict=True)",
        "if not executable.is_file() or not os.access(executable, os.X_OK):",
        "    raise SystemExit('provider executable is invalid')",
        f"if {provider!r} == 'codex':",
        "    installation = Path('/opt/nsc-codex')",
        "    if not executable.is_relative_to(installation):",
        "        raise SystemExit('Codex executable must come from the immutable image installation')",
        "    for path in (executable, *executable.parents):",
        "        metadata = path.stat()",
        "        if metadata.st_uid != 0 or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):",
        "            raise SystemExit('Codex image installation has unsafe ownership or permissions')",
        "        if path == installation:",
        "            break",
    ))


def fenced_docker_command(command: Sequence[str], context: Any, *, role: str,
                          checkout: Path | None = None,
                          output_root: Path | None = None) -> tuple[str, ...]:
    """Route an existing provider invocation into its run's isolated services."""
    argv = tuple(command)
    if argv[:2] != ("docker", "compose") or "run" not in argv:
        raise LocalPublicationRefused("local provider transport requires a Compose run argv")
    position = argv.index("run")
    tail = argv[position:]
    services = [part for part in tail if part in _SERVICES]
    if len(services) != 1:
        raise LocalPublicationRefused("local provider invocation has no exact supported role service")
    path = _root(context) / "provider-runtime" / "compose.json"
    if not path.is_file():
        raise LocalPublicationRefused("local provider runtime has not been prepared")
    # Command-line mounts/network overrides could undo the physical boundary.
    before_service = tail[:tail.index(services[0])]
    index = 0
    while index < len(before_service):
        part = before_service[index]
        if part in {"run", "--rm", "-T", "--no-deps"}:
            index += 1
            continue
        if part == "--volume" and index + 1 < len(before_service):
            mount = before_service[index + 1]
            host, _, target = mount.rpartition(":/")
            allowed = {"execution-output:rw", "nsc-local/run.json:ro", "nsc-pool/checkout-identity.json:ro",
                       "nsc-pool/leases.json:ro", "nsc-pool/profile.json:ro",
                       # The pooled decomposition lease bundle, mounted
                       # read-only exactly as the pooled execution bundles are.
                       "nsc-pool/decomposition-leases.json:ro"}
            if target in allowed and _inside(Path(host).resolve(), _root(context)):
                index += 2
                continue
            if any(mount == f"{project_name(context)}_{provider}-config:/home/agent/.{directory}"
                   for provider, directory in (("claude", "claude"), ("codex", "codex"))):
                index += 2
                continue
        if part == "--env" and index + 1 < len(before_service):
            value = before_service[index + 1]
            if value in {"CODEX_HOME=/home/agent/.codex", "CLAUDE_CONFIG_DIR=/home/agent/.claude"}:
                index += 2
                continue
            if value.startswith("NSC_CODEX_RESUME_SANDBOX_ARGUMENT="):
                # This controls the inner CLI only; container egress stays fenced.
                index += 2
                continue
            if value.startswith(("NSC_CLAUDE_MODEL=", "NSC_OPENAI_CODEX_MODEL=")):
                # The pooled models the host reserved leases for. These pin the
                # round's route to the reservation; they open no transport.
                index += 2
                continue
        raise LocalPublicationRefused("local provider commands may not override runtime mounts or networks")
    if checkout is not None:
        checkout = Path(checkout).resolve()
        source_root = getattr(context, "source_root", None)
        is_exact_source = source_root is not None and checkout == Path(source_root).resolve()
        if not _inside(checkout, _root(context)) and not is_exact_source:
            raise LocalPublicationRefused("provider task checkout is outside its local run namespace")
        position = tail.index(services[0])
        tail = (*tail[:position], "--volume", f"{checkout}:/workspace:ro", *tail[position:])
    if output_root is not None:
        # The only writable surface a decomposition container is given. It is
        # per-task, so the prepared Compose definition cannot name it; bind it
        # here, on the same terms as the read-only checkout above.
        output_root = Path(output_root).resolve()
        if not _inside(output_root, _root(context)):
            raise LocalPublicationRefused("provider output root is outside its local run namespace")
        position = tail.index(services[0])
        tail = (*tail[:position], "--volume", f"{output_root}:/decomposition-output:rw", *tail[position:])
    prepared = ("docker", "compose", "-f", str(path), "-p", project_name(context), *tail)
    _PREPARED_DOCKER_COMMANDS.add(prepared)
    return prepared


def prepare_local_runtime(context: Any, *, source: Path, architect_root: Path,
                          crew_root: Path, providers: Sequence[str],
                          decomposition_root: Path | None = None) -> Path:
    """Write a standalone Compose definition; never merge production networks.

    Preparation is local and deterministic. Only ``start_local_runtime`` may
    contact Docker, and it requires separate explicit live-canary authority.
    Existing authentication stores are mounted read-only by offline seed jobs;
    providers write only newly namespaced session volumes.

    ``decomposition_root`` is the run's review-only proposal tree. It defaults
    to this run's own ``decomposition-output`` directory, so the caller that
    prepares the runtime does not have to know a task yet. The launcher binds
    the exact per-task subdirectory over this one at run time; the definition
    only has to declare the service and its output surface.
    """
    providers = tuple(sorted(set(providers)))
    if not providers or any(provider not in {"claude", "codex"} for provider in providers):
        raise LocalPublicationRefused("invalid local provider topology")
    root = _root(context)
    runtime = root / "provider-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    tls_root = runtime / "tls"
    tls_root.mkdir(exist_ok=True)
    source = Path(source).resolve()
    # The review role binds the architect output over a nested path inside the
    # read-only /workspace mount. Docker cannot create that mountpoint on a
    # read-only bind, and the path is gitignored so a fresh checkout lacks it.
    # Create it (empty, still untracked) in the source now so the mountpoint
    # exists before compose up; otherwise the architect container dies with
    # "make mountpoint .../orchestrator/architect" and the run goes idle.
    (source / "Pipeline" / "ArchitectureReview" / "outputs"
     / "orchestrator" / "architect").mkdir(parents=True, exist_ok=True)
    decomposition_root = Path(decomposition_root or root / "decomposition-output")
    for directory in (architect_root, crew_root, decomposition_root):
        if not _inside(Path(directory).resolve(), root):
            raise LocalPublicationRefused("provider outputs must remain in this exact local namespace")
        Path(directory).mkdir(parents=True, exist_ok=True)
    gateway = source / "Pipeline" / "TaskReviewAgent" / "local_provider_gateway.py"
    if not gateway.is_file():
        raise LocalPublicationRefused("exact source lacks the local provider gateway")
    services: dict[str, Any] = {}
    volumes: dict[str, Any] = {}
    build = {"context": str(source), "dockerfile": "Dockerfile"}
    restrictions = {"cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
                    "read_only": True, "tmpfs": ["/tmp:rw,nosuid,nodev"], "init": True}
    services["gateway"] = {
        **restrictions, "build": build, "working_dir": "/tmp",
        "networks": ["provider_only", "egress"],
        "sysctls": {"net.ipv4.ip_forward": "0"},
        "volumes": [{"type": "bind", "source": str(gateway), "target": "/gateway.py", "read_only": True},
                    {"type": "bind", "source": str(tls_root), "target": "/gateway-tls", "read_only": True}],
        "healthcheck": {"test": ["CMD", "python3", "-c", "import socket; socket.create_connection(('127.0.0.1',8080),2).close()"],
                        "interval": "2s", "timeout": "3s", "retries": 3},
        "command": ["python3", "-u", "/gateway.py"],
    }
    services["seed-tls"] = {
        **restrictions, "build": build, "network_mode": "none", "working_dir": "/tmp",
        "volumes": [{"type": "bind", "source": str(gateway), "target": "/gateway.py", "read_only": True},
                    {"type": "bind", "source": str(tls_root), "target": "/tls"}],
        "command": ["python3", "/gateway.py", "--initialize-tls", "/tls"],
    }
    for provider in providers:
        store = f"{provider}-config"
        seed = f"{provider}-authentication"
        volumes[store] = {}
        credential_volume = _authentication_volume(provider)
        if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", credential_volume) is None:
            raise LocalPublicationRefused("invalid configured provider authentication volume")
        volumes[seed] = {"external": True, "name": credential_volume}
        # Copy credential files only. Old conversations, settings, hooks, and
        # MCP configuration are never inherited by the local provider process.
        services[f"seed-{provider}"] = {
            **restrictions, "build": build, "network_mode": "none", "working_dir": "/tmp",
            "user": "0:0", "cap_add": ["CHOWN", "DAC_OVERRIDE", "FOWNER"],
            "volumes": [{"type": "volume", "source": seed, "target": "/authentication", "read_only": True},
                        {"type": "volume", "source": store, "target": "/sessions"}],
            "command": ["python3", "-c", _credential_seed_script(provider)],
        }
        config_path = "/home/agent/.claude" if provider == "claude" else "/home/agent/.codex"
        services[f"preflight-{provider}"] = {
            **restrictions, "build": build, "network_mode": "none", "working_dir": "/tmp",
            "volumes": [{"type": "volume", "source": store, "target": config_path, "read_only": True}],
            "command": ["python3", "-c", _provider_executable_check_script(provider)],
        }
        environment = {
            "HTTP_PROXY": "http://gateway:8080", "HTTPS_PROXY": "http://gateway:8080",
            "http_proxy": "http://gateway:8080", "https_proxy": "http://gateway:8080",
            "ALL_PROXY": "http://gateway:8080", "NO_PROXY": "", "no_proxy": "",
            "NODE_USE_ENV_PROXY": "1", "DISABLE_AUTOUPDATER": "1",
            "SSL_CERT_FILE": "/nsc-local/ca-bundle.pem", "REQUESTS_CA_BUNDLE": "/nsc-local/ca-bundle.pem",
            "NODE_EXTRA_CA_CERTS": "/nsc-local/ca-bundle.pem", "CURL_CA_BUNDLE": "/nsc-local/ca-bundle.pem",
            "GIT_SSL_CAINFO": "/nsc-local/ca-bundle.pem", "NSC_EXECUTION_OUTPUT_ROOT": "/execution-output",
            "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "true",
            "GIT_CONFIG_KEY_1": "core.filemode", "GIT_CONFIG_VALUE_1": "false",
            "GIT_CONFIG_KEY_2": "core.hooksPath", "GIT_CONFIG_VALUE_2": "/dev/null",
            "NSC_LOCAL_REHEARSAL_CONTAINER": "1",
            "CLAUDE_CONFIG_DIR" if provider == "claude" else "CODEX_HOME": config_path,
        }
        for role in ("review", "exec", "supervisor", "decompose"):
            mounts = [
                {"type": "bind", "source": str(source), "target": "/workspace", "read_only": True},
                {"type": "volume", "source": store, "target": config_path},
                {"type": "bind", "source": str(context.manifest_path), "target": "/nsc-local/run.json", "read_only": True},
                {"type": "bind", "source": str(tls_root / "ca-bundle.pem"), "target": "/nsc-local/ca-bundle.pem", "read_only": True},
            ]
            role_environment = environment
            if role == "review":
                mounts.append({"type": "bind", "source": str(Path(architect_root).resolve()),
                               "target": "/workspace/Pipeline/ArchitectureReview/outputs/orchestrator/architect"})
            if role == "exec":
                mounts.append({"type": "bind", "source": str(Path(crew_root).resolve()), "target": "/execution-output"})
            if role == "decompose":
                # The committed production service's boundary, reproduced for
                # this run: /workspace stays read-only and the only writable
                # task surface is the review-only proposal tree.
                mounts.append({"type": "bind", "source": str(Path(decomposition_root).resolve()),
                               "target": "/decomposition-output"})
                role_environment = {**environment, "NSC_DECOMPOSITION_OUTPUT_ROOT": "/decomposition-output"}
            services[f"{provider}-{role}"] = {
                **restrictions, "build": build, "working_dir": "/workspace", "stdin_open": True,
                "networks": ["provider_only"], "environment": role_environment,
                "volumes": mounts, "command": ["bash"],
            }
    if set(providers) == {"claude", "codex"}:
        # D1B.2 alternates both providers inside one container, so it is not
        # provider scoped: it needs both configuration volumes and both
        # configuration variables, exactly as the committed definition does.
        services["round-robin-decompose"] = {
            **restrictions, "build": build, "working_dir": "/workspace", "stdin_open": True,
            "networks": ["provider_only"],
            "environment": {**environment, "CLAUDE_CONFIG_DIR": "/home/agent/.claude",
                            "CODEX_HOME": "/home/agent/.codex",
                            "NSC_DECOMPOSITION_OUTPUT_ROOT": "/decomposition-output"},
            "volumes": [
                {"type": "bind", "source": str(source), "target": "/workspace", "read_only": True},
                {"type": "volume", "source": "claude-config", "target": "/home/agent/.claude"},
                {"type": "volume", "source": "codex-config", "target": "/home/agent/.codex"},
                {"type": "bind", "source": str(context.manifest_path), "target": "/nsc-local/run.json", "read_only": True},
                {"type": "bind", "source": str(tls_root / "ca-bundle.pem"), "target": "/nsc-local/ca-bundle.pem", "read_only": True},
                {"type": "bind", "source": str(Path(decomposition_root).resolve()), "target": "/decomposition-output"},
            ],
            "command": ["bash"],
        }
    definition = {"services": services, "volumes": volumes,
                  "networks": {"provider_only": {"internal": True}, "egress": {}}}
    path = runtime / "compose.json"
    payload = json.dumps(definition, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise LocalPublicationRefused("persisted local runtime differs from the exact run configuration")
    else:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    return path


def start_local_runtime(context: Any, *, providers: Sequence[str], runner=None) -> None:
    """Initialize only this run's containers after explicit live authorization."""
    if not context.allow_live_canary:
        raise LocalPublicationRefused("local provider execution requires explicit -AllowLiveCanary")
    runner = runner or subprocess.run
    prefix = ("docker", "compose", "-f", str(_root(context) / "provider-runtime" / "compose.json"),
              "-p", project_name(context))
    # Every seed job runs the same Compose verb, so name the service and the
    # external credential volume it reads; a missing store is the usual failure
    # and the operator has to know which provider's.
    commands = [((*prefix, "build"), "provider image build"),
                ((*prefix, "run", "--rm", "-T", "seed-tls"), "seed-tls gateway certificate job")]
    commands.extend(((*prefix, "run", "--rm", "-T", f"seed-{provider}"),
                     f"seed-{provider} from authentication volume {_authentication_volume(provider)}")
                    for provider in providers)
    commands.extend(((*prefix, "run", "--rm", "-T", f"preflight-{provider}"),
                     f"preflight-{provider} image executable") for provider in providers)
    commands.append(((*prefix, "up", "-d", "--wait", "gateway"), "gateway"))
    for command, step in commands:
        _PREPARED_DOCKER_COMMANDS.add(command)
        validate_local_command(command, context)
        result = runner(command, check=False)
        if result.returncode:
            raise LocalPublicationRefused(f"local provider runtime preparation failed: {step}")


def stop_local_gateway(context: Any, *, runner=None) -> None:
    """Stop only this run's gateway after workers have reached a local terminal.

    The caller must establish that there are no active workers. Evidence, task
    checkouts and named session volumes remain available for inspection.
    """
    command = ("docker", "compose", "-f", str(_root(context) / "provider-runtime" / "compose.json"),
               "-p", project_name(context), "stop", "gateway")
    _PREPARED_DOCKER_COMMANDS.add(command)
    validate_local_command(command, context)
    result = (runner or subprocess.run)(command, check=False)
    if result.returncode:
        raise LocalPublicationRefused("local review is ready, but its provider gateway could not be stopped")


def stop_local_runtime(context: Any, *, runner=None) -> dict[str, Any]:
    """Release this run's idle gateway and empty networks, preserving evidence.

    The controller holds its runtime-owner lock through this call and has no
    current or durable worker ownership. Docker inventory independently protects orphan
    providers and foreign attachments. No endpoint is disconnected and removal
    never uses force, volume removal, Compose down, or a global prune.
    """
    project = project_name(context)
    report: dict[str, Any] = {"project": project, "status": "complete",
                              "gateway": "unknown", "networks": {}}
    runner = runner or subprocess.run

    def command(*arguments: str) -> str:
        argv = ("docker", *arguments)
        prepared = (project, argv)
        _PREPARED_CLEANUP_COMMANDS.add(prepared)
        try:
            validate_local_command(argv, context)
            result = runner(argv, check=False, capture_output=True, text=True, timeout=30)
        finally:
            _PREPARED_CLEANUP_COMMANDS.discard(prepared)
        if result.returncode != 0:
            raise LocalPublicationRefused("Docker cleanup command failed: " + " ".join(arguments[:2]))
        if not isinstance(result.stdout, str):
            raise LocalPublicationRefused("Docker cleanup returned invalid output")
        return result.stdout

    def identifiers(*arguments: str) -> list[str]:
        values = command(*arguments).splitlines()
        if len(set(values)) != len(values) or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in values):
            raise LocalPublicationRefused("Docker cleanup inventory has invalid identities")
        return values

    def containers() -> list[str]:
        return identifiers("container", "ls", "--all", "--no-trunc", "--filter",
                           "label=com.docker.compose.project=" + project, "--format", "{{.ID}}")

    def gateway_metadata(identifier: str) -> dict[str, Any]:
        # Request only lifecycle identity, never container environment/config.
        template = ('{"Id":{{json .Id}},"Name":{{json .Name}},'
                    '"Project":{{json (index .Config.Labels "com.docker.compose.project")}},'
                    '"Service":{{json (index .Config.Labels "com.docker.compose.service")}},'
                    '"Running":{{json .State.Running}}}')
        value = json.loads(command("container", "inspect", "--format", template, identifier))
        if (not isinstance(value, dict) or value.get("Id") != identifier
                or value.get("Project") != project or value.get("Service") != "gateway"
                or value.get("Name") not in {f"/{project}-gateway-1", f"/{project}_gateway_1"}
                or type(value.get("Running")) is not bool):
            raise LocalPublicationRefused("Docker cleanup cannot prove the exact run gateway")
        return value

    def network_metadata(identifier: str, logical: str) -> dict[str, Any]:
        values = json.loads(command("network", "inspect", identifier))
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
            raise LocalPublicationRefused("Docker cleanup returned invalid network metadata")
        value = values[0]
        labels = value.get("Labels")
        endpoints = value.get("Containers")
        if (value.get("Id") != identifier or value.get("Name") != project + "_" + logical
                or not isinstance(labels, dict) or labels.get("com.docker.compose.project") != project
                or labels.get("com.docker.compose.network") != logical
                or value.get("Driver") != "bridge" or value.get("Scope") != "local"
                or not isinstance(endpoints, dict)
                or any(re.fullmatch(r"[0-9a-f]{64}", key) is None for key in endpoints)):
            raise LocalPublicationRefused("Docker cleanup cannot prove the exact run network")
        return value

    try:
        owned_containers = containers()
        if len(owned_containers) > 1:
            report.update(status="retained", gateway="retained_other_containers")
            return report
        gateway = owned_containers[0] if owned_containers else None
        if gateway is not None:
            gateway_metadata(gateway)
            report["gateway"] = "present"
        else:
            report["gateway"] = "absent"
        networks = {}
        for logical in ("provider_only", "egress"):
            name = project + "_" + logical
            found = identifiers("network", "ls", "--no-trunc", "--filter", "name=^" + name + "$",
                                "--format", "{{.ID}}")
            if len(found) > 1:
                raise LocalPublicationRefused("Docker cleanup found ambiguous run networks")
            if not found:
                report["networks"][logical] = "absent"
                continue
            metadata = network_metadata(found[0], logical)
            networks[logical] = found[0]
            if set(metadata["Containers"]) - ({gateway} if gateway else set()):
                report.update(status="retained", gateway="retained_attached_containers")
                report["networks"][logical] = "retained_attached"
                return report
        if gateway is not None:
            # Recheck immediately before stopping, retaining a concurrently
            # visible provider. All controllers also share the runtime lock.
            if containers() != [gateway]:
                report.update(status="retained", gateway="retained_inventory_changed")
                return report
            metadata = gateway_metadata(gateway)
            if metadata["Running"]:
                report["gateway"] = "stop_unconfirmed"
                command("container", "stop", "--timeout", "10", gateway)
            report["gateway"] = "remove_unconfirmed"
            command("container", "rm", gateway)
            report["gateway"] = "removed"
        for logical, identifier in networks.items():
            try:
                if network_metadata(identifier, logical)["Containers"]:
                    report["networks"][logical] = "retained_attached"
                    if report["status"] != "failed":
                        report["status"] = "retained"
                    continue
                # By immutable ID, without force: Docker refuses attachments
                # arriving after inspection instead of disconnecting them.
                command("network", "rm", identifier)
                report["networks"][logical] = "removed"
            except (OSError, ValueError, subprocess.SubprocessError, LocalPublicationRefused) as exc:
                report["networks"][logical] = "failed"
                report.setdefault("errors", []).append(type(exc).__name__ + ": " + str(exc))
                report["status"] = "failed"
    except (OSError, ValueError, subprocess.SubprocessError, LocalPublicationRefused) as exc:
        report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
    return report
