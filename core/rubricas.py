import json
from pathlib import Path

RUBRICAS_DIR = Path(__file__).resolve().parent.parent / "data" / "rubricas"


def cargar_rubricas() -> dict[str, dict]:
    """Devuelve las rúbricas disponibles indexadas por id de AE."""
    rubricas = {}
    for ruta in sorted(RUBRICAS_DIR.glob("*.json")):
        rubrica = json.loads(ruta.read_text(encoding="utf-8"))
        rubricas[rubrica["id"]] = rubrica
    return rubricas


def nombres_indicadores(rubrica: dict) -> dict[str, str]:
    return {i["id"]: i["nombre"] for i in rubrica["indicadores"]}
