import json
from pathlib import Path

RUBRICAS_DIR = Path(__file__).resolve().parent.parent / "data" / "rubricas"


NIVELES = {"1", "2", "3", "4"}
ESTADOS_VALIDACION = {"pendiente", "en revision", "validada"}


def validar_rubrica(r: dict) -> list[str]:
    """Revisa la estructura de una rúbrica. Devuelve la lista de errores (vacía si es válida)."""
    errores = []
    for campo in ("id", "nombre", "programa", "descripcion", "nivel_minimo", "niveles", "indicadores"):
        if campo not in r:
            errores.append(f"falta el campo '{campo}'")
    if errores:
        return errores

    if set(r["niveles"]) != NIVELES:
        errores.append("'niveles' debe definir exactamente los niveles 1 a 4")
    if r["nivel_minimo"] not in (1, 2, 3, 4):
        errores.append("'nivel_minimo' debe ser un entero del 1 al 4")
    if not r["indicadores"]:
        errores.append("la rúbrica no tiene indicadores")

    ids = [i.get("id") for i in r["indicadores"]]
    if len(ids) != len(set(ids)):
        errores.append("hay indicadores con id repetido")
    for i in r["indicadores"]:
        nombre = i.get("id", "?")
        for campo in ("id", "nombre", "descripcion", "niveles", "palabras_clave"):
            if campo not in i:
                errores.append(f"indicador {nombre}: falta '{campo}'")
        if "niveles" in i and set(i["niveles"]) != NIVELES:
            errores.append(f"indicador {nombre}: debe describir los niveles 1 a 4")

    fuentes = r.get("fuentes")
    if fuentes:
        pesos = [f.get("peso", 0) for f in fuentes.values()]
        if abs(sum(pesos) - 1) > 1e-6:
            errores.append(f"los pesos de 'fuentes' deben sumar 1 (suman {sum(pesos):g})")
        cal = fuentes.get("calificaciones")
        if cal:
            desdes = [e["desde"] for e in cal.get("escala", [])]
            if not desdes or desdes[0] != 0 or desdes != sorted(desdes):
                errores.append("la escala de calificaciones debe iniciar en 0 y ser ascendente")
            if any(e["nivel"] not in (1, 2, 3, 4) for e in cal.get("escala", [])):
                errores.append("la escala de calificaciones solo admite niveles 1 a 4")
            if not cal.get("asignaturas"):
                errores.append("'fuentes.calificaciones' debe listar las asignaturas que tributan al AE")
        cen = fuentes.get("ceneval")
        if cen:
            if not cen.get("areas"):
                errores.append("'fuentes.ceneval' debe listar las áreas que tributan al AE")
            if any(v not in (1, 2, 3, 4) for v in cen.get("niveles", {}).values()):
                errores.append("'fuentes.ceneval.niveles' solo admite niveles 1 a 4")

    val = r.get("validacion")
    if val and val.get("estado") not in ESTADOS_VALIDACION:
        errores.append(f"'validacion.estado' debe ser uno de: {', '.join(sorted(ESTADOS_VALIDACION))}")
    return errores


def _leer_todas() -> tuple[dict[str, dict], dict[str, list[str]]]:
    rubricas, errores = {}, {}
    for ruta in sorted(RUBRICAS_DIR.glob("*.json")):
        try:
            rubrica = json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errores[ruta.name] = [f"JSON inválido: {e}"]
            continue
        problemas = validar_rubrica(rubrica)
        if problemas:
            errores[ruta.name] = problemas
        else:
            rubricas[rubrica["id"]] = rubrica
    return rubricas, errores


def cargar_rubricas() -> dict[str, dict]:
    """Devuelve las rúbricas válidas indexadas por id de AE. Las inválidas se reportan con errores_rubricas()."""
    return _leer_todas()[0]


def errores_rubricas() -> dict[str, list[str]]:
    """Errores de estructura por archivo de rúbrica."""
    return _leer_todas()[1]


def nombres_indicadores(rubrica: dict) -> dict[str, str]:
    return {i["id"]: i["nombre"] for i in rubrica["indicadores"]}
