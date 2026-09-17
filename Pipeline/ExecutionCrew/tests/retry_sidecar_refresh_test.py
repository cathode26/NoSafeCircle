"""P34: seed_retry_candidate must refresh pipeline-owned sidecars in a seeded, uncommitted
prior candidate.patch to the current unity_meta_bytes contract, not re-deliver whatever
bytes a prior run wrote (e.g. a pre-P34 GUID-only texture stub). A committed sidecar is
tracked source, not pipeline output, so an already_present retry against a stale committed
sidecar must fail closed instead (round 3), naming the exact path so the operator can commit
the current unity_meta_bytes contract for it and retry -- which the same already_present
retry must then accept, since a corrected sidecar need not equal the reconstructed prior
candidate bytes (round 3 fix)."""
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
    CrewBlocked, RetryContext, seed_retry_candidate, snapshot, unity_meta_bytes, unity_meta_guid, paths_patch,
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

    def test_stale_texture_sidecar_committed_pre_p34_blocks_already_present_retry(self):
        # A pre-P34 run's candidate -- a GUID-only texture stub plus an already-correct .cs
        # stub -- was committed to source verbatim (not just seeded into a disposable clone).
        # A committed sidecar is tracked source, not pipeline output: downstream readers
        # (local_candidate_commit._verified_pipeline_generated_paths, load_retry_context)
        # only ever treat pipeline-generated paths as companions of newly-approved files, so
        # rewriting it here cannot be surfaced to them. Retrying after P34 changed the meta
        # contract must fail closed instead of silently rewriting committed history (P34
        # round 3), even though the paths otherwise match the already_present criteria.
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

        committed_png_meta = (self.clone / PNG_META).read_bytes()

        with self.assertRaises(CrewBlocked) as caught:
            seed_retry_candidate(self.clone, baseline, retry)
        self.assertIn(PNG_META, str(caught.exception))
        self.assertNotIn(CS_META, str(caught.exception))

        # Nothing in the clone was written: the stale sidecar is untouched, and there is no
        # working-tree change at all.
        self.assertEqual((self.clone / PNG_META).read_bytes(), committed_png_meta)
        self.assertEqual((self.clone / PNG_META).read_bytes(), _stub_meta(PNG_PATH))
        self.assertEqual(_git(self.clone, "status", "--porcelain"), "")
        self.assertEqual(snapshot(self.clone), baseline)

        # Step 2: the operator follows the CrewBlocked message and commits the current
        # unity_meta_bytes for the stale sidecar, exactly as instructed.
        (self.clone / PNG_META).write_bytes(unity_meta_bytes(PNG_PATH))
        _git(self.clone, "add", PNG_META)
        _git(self.clone, "commit", "-qm", "operator commits corrected meta")
        corrected_baseline = snapshot(self.clone)

        # Step 3: the same retry must now resume -- already_present, nothing written -- instead
        # of being blocked again by the reconstructed-prior-candidate equivalence check (P34
        # round 3 fix: a corrected sidecar is accepted against the current unity_meta_bytes
        # contract even though it no longer equals the reconstructed prior candidate bytes).
        result = seed_retry_candidate(self.clone, corrected_baseline, retry)
        self.assertEqual(result, "already_present")
        self.assertEqual((self.clone / PNG_META).read_bytes(), unity_meta_bytes(PNG_PATH))
        self.assertEqual(_git(self.clone, "status", "--porcelain"), "")
        self.assertEqual(snapshot(self.clone), corrected_baseline)

        # Step 4 (guard): committing some other, non-conformant meta still refuses -- the
        # relaxation only accepts the current unity_meta_bytes contract, not any edit.
        (self.clone / PNG_META).write_bytes(b"fileFormatVersion: 2\nguid: 0000000000000000deadbeef000000\n")
        _git(self.clone, "add", PNG_META)
        _git(self.clone, "commit", "-qm", "operator commits an unrelated, non-conformant meta")
        other_baseline = snapshot(self.clone)
        with self.assertRaises(CrewBlocked) as diverged:
            seed_retry_candidate(self.clone, other_baseline, retry)
        # The refusal names the sidecar so the operator knows what to repair.
        self.assertIn(PNG_META, str(diverged.exception))
        self.assertEqual(_git(self.clone, "status", "--porcelain"), "")
        self.assertEqual(snapshot(self.clone), other_baseline)

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
