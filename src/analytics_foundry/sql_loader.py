"""Load SQL artifacts from sql/ directory. Medallion flow: bronze → silver → gold."""

from pathlib import Path

_SQL_ROOT = Path(__file__).resolve().parent.parent.parent / "sql"


def get_sql_root() -> Path:
    """Return path to sql/ directory."""
    return _SQL_ROOT


def list_sql_files(layer: str) -> list[str]:
    """List .sql filenames in sql/<layer>/ (e.g. bronze, silver, gold)."""
    folder = _SQL_ROOT / layer
    if not folder.is_dir():
        return []
    return [f.name for f in folder.iterdir() if f.suffix == ".sql"]


def read_sql(layer: str, name: str) -> str:
    """Read contents of sql/<layer>/<name>.sql."""
    path = _SQL_ROOT / layer / f"{name}.sql" if not name.endswith(".sql") else _SQL_ROOT / layer / name
    return path.read_text(encoding="utf-8")


def medallion_layers() -> list[str]:
    """Return medallion layer order: bronze, silver, gold."""
    return ["bronze", "silver", "gold"]
