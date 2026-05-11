# Catalog Manifest for ❤Music

This document describes the structure and workflow for the `catalog/manifest.json` file, which provides an auditable, agent-discoverable index of all catalog media files.

## Manifest Schema

- `manifest_version`: Integer version of the manifest schema
- `generated_at`: ISO8601 UTC timestamp when manifest was generated
- `catalog`: List of catalog entries, each with:
  - `filename`: File name
  - `path`: Path relative to `catalog/`
  - `size`: File size in bytes
  - `date_added`: File creation date (UTC, ISO8601)
  - `source`: (Optional) Source of file (e.g., upload, import, agent)
  - `artist`: (Optional) Artist name
  - `album`: (Optional) Album name
  - `genre`: (Optional) Genre
  - `duration`: (Optional) Duration in seconds
  - `bitrate`: (Optional) Bitrate in kbps

## Regeneration Workflow

To regenerate the manifest after adding/removing files:

1. Run the script:
   ```sh
   python src/utils/manifest_generator.py
   ```
2. The script scans all files in `catalog/` (excluding `manifest.json`) and updates the manifest.
3. Commit the updated `manifest.json` to git.

## Use Cases
- Agent workflows: discover catalog contents, audit changes, drive batch operations
- Human audit: verify catalog state, track additions/removals
- Downstream tools: performance tracking, setlist generation, distribution

## Notes
- Only `.json` files are tracked; media files (e.g., `.mp3`) are gitignored
- Manifest is idempotent: re-running the script produces the same result if files are unchanged
