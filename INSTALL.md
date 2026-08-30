# Install

This package is laid out relative to the No Safe Circle repository root.

From PowerShell, after extracting the ZIP:

```powershell
Set-Location "C:\NSC\NSC\NoSafeCircle"

Copy-Item `
  -LiteralPath "<EXTRACTED-PACKAGE>\Docs\AI-Pipeline\Historical-Context-Sessions" `
  -Destination ".\Docs\AI-Pipeline" `
  -Recurse `
  -Force

git status --short
```

Before committing, inspect the new files and decide whether you want all three raw transcripts in Git. The structured context files are the important part; `raw/` is optional long-term archaeology.
