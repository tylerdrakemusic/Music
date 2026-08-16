# ❤Music Database Backup Inventory

`src/config/database_backup_inventory.json` is the ❤Music contribution to the
shared manifest-driven local database backup contract.

The inventory identifies the canonical Music store with the redacted locator
`music/heartmusic-store` and discovery basename `heartmusic.db`. It records
that the file is SQLCipher-encrypted and names only the existing
`HEARTMUSIC_DB_KEY` environment variable. It contains no filesystem path, key
value, catalog records, or database contents.

The provider-neutral backup runner can select approved entries from this
inventory. Adding another approved Music database requires another inventory
entry, not bespoke backup code. The canonical connection remains owned by
`src/utils/init_db.py` and continues to use `sqlcipher3` with
`HEARTMUSIC_DB_KEY`.

`src/data/backups/**` and `data/legacy_heartmusic.db` remain explicitly
excluded. Existing plaintext migration artifacts are not eligible for future
backup discovery.