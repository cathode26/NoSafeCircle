"""P34 FIX_FIRST: seed_retry_candidate must refresh pipeline-owned sidecars in a seeded
prior candidate.patch to the current unity_meta_bytes contract, not re-deliver whatever
bytes a prior run wrote (e.g. a pre-P34 GUID-only texture stub)."""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    RetryContext, seed_retry_candidate, snapshot, unity_meta_bytes, unity_meta_guid, paths_patch,
)
from Pipeline.TaskExecution.contracts import TaskContractIdentity  # noqa: E402

TEMP_ROOT = Path(os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir())

PNG_PATH = "Assets/X/a.png"
PNG_META = "Assets/X/a.png.meta"
CS_PATH = "Assets/X/b.cs"
CS_META = "Assets/X/b.cs.meta"


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(root, *args, **kw):
    return subprocess.run(("git", "-C", str(root), *args), check=True, creationflags=NO_WINDOW,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw).stdout.strip()


def _stub_meta(path):
    return f"fileFormatVersion: 2\nguid: {unity_meta_guid(path)}\n".encode("ascii")


class RetrySidecarRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nsc-retry-sidecar-", dir=str(TEMP_ROOT))
        self.addCleanup(self.tmp.cleanup)
        self.clone = Path(self.tmp.name) / "clone"
        self.clone.mkdir()
        subprocess.run(("git", "init", "-q", str(self.clone)), check=True, creationflags=NO_WINDOW)
        # Match clone_exact: the crew's disposable clone applies patches with autocrlf off,
        # so a host-wide autocrlf=true must not rewrite the seeded bytes here.
        _git(self.clone, "config", "core.autocrlf", "false")
        _git(self.clone, "config", "user.name", "Retry Sidecar Test")
        _git(self.clone, "config", "user.email", "retry-sidecar-test@example.invalid")
        (self.clone / "Assets" / "X").mkdir(parents=True)
        (self.clone / "Assets" / "X" / "keep.txt").write_text("keep\n", encoding="ascii")
        _git(self.clone, "add", ".")
        _git(self.clone, "commit", "-qm", "initial")
        self.head = _git(self.clone, "rev-parse", "HEAD")

    def _write(self, relative, data):
        path = self.clone / relative
        path.write_bytes(data)

    def test_stale_texture_sidecar_is_refreshed_to_current_contract_on_seed(self):
        # A pre-P34 run produced a candidate with a GUID-only texture stub and an
        # already-correct .cs stub. Both are new pipeline-owned files.
        self._write(PNG_PATH, b"not a real png, just a few bytes")
        self._write(PNG_META, _stub_meta(PNG_PATH))
        self._write(CS_PATH, b"public class B {}\n")
        self._write(CS_META, unity_meta_bytes(CS_PATH))

        new_paths = (PNG_PATH, PNG_META, CS_PATH, CS_META)
        candidate_bytes = paths_patch(self.clone, self.head, new_paths, new_paths=new_paths)

        for relative in new_paths:
            (self.clone / relative).unlink()

        baseline = snapshot(self.clone)
        self.assertEqual(baseline.head, self.head)

        retry = RetryContext(
            prior_run_id="prior-run",
            prior_source_head=self.head,
            prior_contract_identity=TaskContractIdentity(
                path="Tasks/TEST.yaml", revision=1, sha256=hashlib.sha256(b"contract").hexdigest(),
            ),
            task_id="TEST",
            provider="test-provider",
            execution_model=None,
            execution_reasoning_effort=None,
            crew_profile="default",
            validation_profile="default",
            implementation_paths=(),
            test_paths=(),
            new_implementation_paths=(PNG_PATH, CS_PATH),
            new_test_paths=(),
            candidate_bytes=candidate_bytes,
            candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
            candidate_paths=tuple(sorted(new_paths)),
            candidate_sidecars=(PNG_META, CS_META),
            feedback_bytes=b"",
            feedback_text="",
            feedback_sha256=hashlib.sha256(b"").hexdigest(),
            provider_allowlist=None,
            quota_fallback_provider=None,
        )

        result = seed_retry_candidate(self.clone, baseline, retry)

        self.assertEqual(result, "applied")
        # The stale GUID-only texture stub must be replaced by the current contract's bytes.
        self.assertEqual((self.clone / PNG_META).read_bytes(), unity_meta_bytes(PNG_PATH))
        self.assertNotEqual((self.clone / PNG_META).read_bytes(), _stub_meta(PNG_PATH))
        # A sidecar that already matched the current contract stays byte-identical.
        self.assertEqual((self.clone / CS_META).read_bytes(), unity_meta_bytes(CS_PATH))

    def test_stale_texture_sidecar_committed_pre_p34_is_refreshed_on_already_present_retry(self):
        # A pre-P34 run's candidate -- a GUID-only texture stub plus an already-correct .cs
        # stub -- was committed to source verbatim (not just seeded into a disposable clone).
        # Retrying it after P34 changed the meta contract must take the already_present
        # branch (the paths differ from prior_source_head, but exactly match the
        # reconstructed prior candidate post-image) and still refresh the stale stub.
        self._write(PNG_PATH, b"not a real png, just a few bytes")
        self._write(PNG_META, _stub_meta(PNG_PATH))
        self._write(CS_PATH, b"public class B {}\n")
        self._write(CS_META, unity_meta_bytes(CS_PATH))

        new_paths = (PNG_PATH, PNG_META, CS_PATH, CS_META)
        candidate_bytes = paths_patch(self.clone, self.head, new_paths, new_paths=new_paths)
        prior_source_head = self.head

        _git(self.clone, "add", *new_paths)
        _git(self.clone, "commit", "-qm", "pre-P34 candidate committed exactly")
        committed_head = _git(self.clone, "rev-parse", "HEAD")
        self.assertNotEqual(committed_head, prior_source_head)

        baseline = snapshot(self.clone)
        self.assertEqual(baseline.head, committed_head)

        retry = RetryContext(
            prior_run_id="prior-run",
            prior_source_head=prior_source_head,
            prior_contract_identity=TaskContractIdentity(
                path="Tasks/TEST.yaml", revision=1, sha256=hashlib.sha256(b"contract").hexdigest(),
            ),
            task_id="TEST",
            provider="test-provider",
            execution_model=None,
            execution_reasoning_effort=None,
            crew_profile="default",
            validation_profile="default",
            implementation_paths=(),
            test_paths=(),
            new_implementation_paths=(PNG_PATH, CS_PATH),
            new_test_paths=(),
            candidate_bytes=candidate_bytes,
            candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
            candidate_paths=tuple(sorted(new_paths)),
            candidate_sidecars=(PNG_META, CS_META),
            feedback_bytes=b"",
            feedback_text="",
            feedback_sha256=hashlib.sha256(b"").hexdigest(),
            provider_allowlist=None,
            quota_fallback_provider=None,
        )

        result = seed_retry_candidate(self.clone, baseline, retry)

        self.assertEqual(result, "already_present")
        # The stale, already-committed GUID-only texture stub is refreshed in place.
        self.assertEqual((self.clone / PNG_META).read_bytes(), unity_meta_bytes(PNG_PATH))
        self.assertNotEqual((self.clone / PNG_META).read_bytes(), _stub_meta(PNG_PATH))
        # Its GUID line -- the only part references depend on -- survives the refresh.
        guid_line = f"guid: {unity_meta_guid(PNG_PATH)}".encode("ascii")
        self.assertIn(guid_line, (self.clone / PNG_META).read_bytes())
        # A sidecar that already matched the current contract stays byte-identical.
        self.assertEqual((self.clone / CS_META).read_bytes(), unity_meta_bytes(CS_PATH))
        # Only the stale sidecar is a working-tree change; the conformant one and the
        # already-committed candidate files themselves are left alone.
        touched = {
            line.split()[-1] for line in _git(self.clone, "status", "--porcelain").splitlines()
        }
        self.assertEqual(touched, {PNG_META})

    def test_already_conformant_committed_sidecar_is_unchanged_on_already_present_retry(self):
        # Guard: when the committed sidecar already matches the current contract (e.g. a
        # non-texture .cs stub), an already_present retry must return already_present and
        # touch nothing in the clone.
        self._write(CS_PATH, b"public class B {}\n")
        self._write(CS_META, unity_meta_bytes(CS_PATH))

        new_paths = (CS_PATH, CS_META)
        candidate_bytes = paths_patch(self.clone, self.head, new_paths, new_paths=new_paths)
        prior_source_head = self.head

        _git(self.clone, "add", *new_paths)
        _git(self.clone, "commit", "-qm", "conformant candidate committed exactly")
        committed_head = _git(self.clone, "rev-parse", "HEAD")

        baseline = snapshot(self.clone)
        self.assertEqual(baseline.head, committed_head)

        retry = RetryContext(
            prior_run_id="prior-run",
            prior_source_head=prior_source_head,
            prior_contract_identity=TaskContractIdentity(
                path="Tasks/TEST.yaml", revision=1, sha256=hashlib.sha256(b"contract").hexdigest(),
            ),
            task_id="TEST",
            provider="test-provider",
            execution_model=None,
            execution_reasoning_effort=None,
            crew_profile="default",
            validation_profile="default",
            implementation_paths=(),
            test_paths=(),
            new_implementation_paths=(CS_PATH,),
            new_test_paths=(),
            candidate_bytes=candidate_bytes,
            candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
            candidate_paths=tuple(sorted(new_paths)),
            candidate_sidecars=(CS_META,),
            feedback_bytes=b"",
            feedback_text="",
            feedback_sha256=hashlib.sha256(b"").hexdigest(),
            provider_allowlist=None,
            quota_fallback_provider=None,
        )

        result = seed_retry_candidate(self.clone, baseline, retry)

        self.assertEqual(result, "already_present")
        self.assertEqual((self.clone / CS_META).read_bytes(), unity_meta_bytes(CS_PATH))
        self.assertEqual(_git(self.clone, "status", "--porcelain"), "")
        self.assertEqual(snapshot(self.clone), baseline)


if __name__ == "__main__":
    unittest.main()
