# SQL artifacts (medallion)

Bronze → Silver → Gold view/transform definitions. Unity Catalog–friendly; AWS/Databricks-ready.

- **bronze/** — raw source tables (append-only; source-specific schema).
- **silver/** — cleaned, conformed, deduplicated (canonical entities).
- **gold/** — business-level aggregates for API and analytics.

Run order: bronze ingest (adapter) → silver transforms → gold views.
