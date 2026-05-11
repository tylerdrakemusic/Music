# Agent Discovery: Catalog Manifest

## Overview
The `catalog/manifest.json` file provides a machine-readable index of all catalog media files for agent workflows. All ❤music agents should use this manifest for catalog discovery, auditing, and batch operations.

## How to Use
- **Import the manifest:**
  ```python
  import json
  with open('catalog/manifest.json', encoding='utf-8') as f:
      manifest = json.load(f)
  # manifest['catalog'] is a list of entries
  ```
- **Regenerate:** Use `src/utils/manifest_generator.py` to update the manifest after catalog changes.
- **Idempotency:** The manifest can be regenerated at any time; agents should not modify it directly.

## Example Usage Patterns
- Catalog orchestrator: enumerate all files for batch tagging or migration
- Performance tracker: cross-reference catalog entries with play logs
- Distribution agent: verify catalog state before publishing

## Agents
The following agents are expected to use the manifest:
- `❤music-catalog` (catalog operations)
- `❤music-production` (batch processing, metadata)
- `❤music-performance` (setlist, play tracking)
- Any new agent requiring catalog state

## Integration Notes
- Manifest is always up to date if script is run after catalog changes
- Do not parse the catalog directory directly; always use the manifest for consistency
