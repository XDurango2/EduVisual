import pytest

from core import db
from core.rubricas import cargar_rubricas


@pytest.fixture(autouse=True)
def base_temporal(tmp_path, monkeypatch):
    """Cada prueba usa una base SQLite nueva; nunca toca data/eduvisual.db."""
    from core import seed

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "prueba.db")
    monkeypatch.setattr(seed, "EJEMPLOS_DIR", tmp_path / "ejemplos")
    db.init_db()


@pytest.fixture
def rubricas():
    return cargar_rubricas()
