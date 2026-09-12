# migrations — Alembic schema history

## Purpose

Versioned schema evolution for the default-bind SQLite database, applied through the backup-first wrapper script.

## Ownership

- `versions/` — 6 revisions, strictly linear, head `4ff671f5bcdc`:
  `cb243cbec50e` (initial: full default-bind schema, incl. the unified `portions` table) → `3978a31de65b` (`seq_num` on recipe ingredients) → `b2a84814143e` (`final_weight_grams` on recipes) → `9dc6a1eef6f6` (nullable `user_id` on `my_meals`) → `8f01092d5559` (`user_id` on `food_category`) → `4ff671f5bcdc` (`is_placeholder` on `my_foods`).
- `env.py` — overrides `sqlalchemy.url` from the live Flask engine at :38, so the URLs in `/alembic.ini` (:87-88, root-relative `sqlite:///user_data.db`) are dead and misleading. Do not trust or "fix" them into active use.
- `script.py.mako`, `alembic.ini` template-side config.
- Not owned here: the model definitions (`/models.py`, root-owned), `import_usda_data.py` + `/schema_usda.sql`, which create the whole `usda` bind outside Alembic.

## Local Contracts

- Alembic manages the **default bind only**. Tables with `__bind_key__ = "usda"` (`foods`, `nutrients`, `food_nutrients`) are created by `import_usda_data.py` and `schema_usda.sql`; never add them to a migration, and inspect a generated revision for spurious `create_table`/`drop_table` ops against them before committing.
- `env.py` does not set `render_as_batch`. SQLite cannot `ALTER COLUMN`, so any column type/nullability change must be hand-edited into `op.batch_alter_table(...)` — otherwise the migration fails at apply time, not at generate time.
- Autogenerate is not trustworthy for data: review every generated revision, and add explicit `op.execute`/`op.bulk_insert` backfills where a new non-null column needs values. The initial revision was hand-adjusted after generation and is the model to follow.
- Never hand-edit or renumber an already-shared revision; add a new one. History must stay single-headed — two files claiming the same `down_revision` break `flask db upgrade`.
- `flask db migrate` writes into this tracked directory. Never run it from an ops script: `seed_usda.sh:30` does exactly that and pollutes git history with an environment-specific revision.
- Tests use `db.create_all()` and never touch Alembic, so the suite cannot validate a migration. Apply every new revision against a copy of a real `persistent/user_data.db`.

## Work Guidance

- Generate with `flask db migrate -m "<short description>"`, then apply with `/safe_upgrade.sh`, which copies the DB to `persistent/backups/` first. Plain `flask db upgrade` skips that backup.
- `safe_upgrade.sh` only backs up the hard-coded path `persistent/user_data.db`; if `DATABASE_URL` points elsewhere it prints "skipping backup (first run)" and migrates anyway. Confirm the backup exists before continuing.
- Down-migrations exist for every revision; keep `downgrade()` meaningful even though rollback is manual (no script restores a `.bak`).
- Backups accumulate unbounded in `persistent/backups/`; prune when touching this area.

## Verification

```bash
cp persistent/user_data.db /tmp/mig_check.db
DATABASE_URL="sqlite:////tmp/mig_check.db" flask db upgrade
DATABASE_URL="sqlite:////tmp/mig_check.db" flask db current   # must equal the new head
```

## Child DOX Index

No child docs.
