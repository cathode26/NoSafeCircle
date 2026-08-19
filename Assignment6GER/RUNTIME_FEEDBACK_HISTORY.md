# Runtime Feedback History Patch

Runtime feedback is now append-only.

Files are preserved as:

- `runtime_feedback000.json`
- `runtime_feedback001.json`
- `runtime_feedback002.json`
- ...

A numbered runtime feedback file is never overwritten by `ger_pipeline.py`.

For the current second Unity failure, run:

```powershell
docker compose run --rm claude python3 Assignment6GER/ger_pipeline.py --runtime-feedback Assignment6GER/outputs/runtime_feedback001.json
```

Future Unity failures should be recorded as the next sequential file and passed
explicitly with `--runtime-feedback`.

If an unnumbered feedback file is ever supplied, the pipeline automatically
copies it into the next available numbered history file before refinement.
