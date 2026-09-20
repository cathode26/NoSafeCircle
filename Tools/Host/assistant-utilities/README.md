# Preserved AssistantControl host utilities

Source imported on 2026-09-20 from `C:/NSC/NoSafeCircle-AssistantCheckouts/.assistant-control`. This is the tracked source location for future review and maintenance. Existing live files remain untouched; no launcher or consumer has been redirected here.

**These copies were inspected as text and verified by SHA-256. They were not executed, behavior-tested, or made supported operational entry points.** Historical task authorization in a script is not permission to run it today.

| Preserved source | Purpose and current status |
| --- | --- |
| [parse_pixellab_logs.py](originals/parse_pixellab_logs.py) | Reusable candidate: reads named Docker container logs and extracts PixelLab job metadata. Requires Docker and access to the named containers. Output can contain prompt descriptions and errors; this import includes no logs. |
| [Set-PixelLabClaudeMcp.ps1](originals/Set-PixelLabClaudeMcp.ps1) | Reusable candidate: prompts for a token, modifies Claude user configuration, and writes a configuration backup. The source contains no token value. Configuration files and backups are private runtime material and are not included. |
| [build_door_contact_sheet.py](historical/NSC-065/build_door_contact_sheet.py) | Historical NSC-065 source: hard-coded checkout and door-image paths; writes a contact sheet when executed or imported. Depends on Pillow. |
| [finalize_door_selection.py](historical/NSC-065/finalize_door_selection.py) | Historical NSC-065 source: copies selected images and writes task art inventory and generation notes when executed or imported. It contains dated job IDs and selection claims, not current approval. |
| [controller-run-nsc-066.ps1](historical/NSC-066/controller-run-nsc-066.ps1) | Historical NSC-066 launcher: hard-coded live paths, old `run-graph` command, and an explicit provider-spend flag. Do not use it as a current startup command. |

Before promoting a reusable candidate, give it an explicit supported interface, validate its effects under the repository's current operator rules, and document dependencies. No such behavior changes are part of this source-preservation import.

See the [agent-operations index](../../../Docs/AI-Pipeline/Agent-Operations/README.md) and [source map](../../../Docs/AI-Pipeline/Agent-Operations/source-map.json) for import scope and exact hashes. Do not import live task JSON records, credential files, provider session history, or runtime logs into this directory.
