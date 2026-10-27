"""Nivel de adopción de un Atributo de Egreso combinando sus fuentes (avance de RF-004).

Cada fuente se convierte a la escala de la rúbrica (niveles 1-4):
- evidencias: nivel final del docente o, si no hay revisión, el sugerido por el motor;
- calificaciones: según la escala de la rúbrica (fuentes.calificaciones.escala);
- CENEVAL: según el desempeño por área (fuentes.ceneval.niveles).
El índice combinado pondera el % de cumplimiento de cada fuente con sus pesos, re-normalizados
entre las fuentes que tienen datos.
"""
import pandas as pd

from core import db

ETIQUETAS = {"evidencias": "Evidencias (rúbrica)", "calificaciones": "Calificaciones", "ceneval": "CENEVAL"}


def nivel_por_calificacion(calificacion: float, escala: list[dict]) -> int:
    nivel = escala[0]["nivel"]
    for tramo in escala:
        if calificacion >= tramo["desde"]:
            nivel = tramo["nivel"]
    return nivel


def niveles_por_fuente(rubrica: dict) -> pd.DataFrame:
    """Una fila por registro con columnas: fuente, alumno, nivel."""
    fuentes = rubrica.get("fuentes", {})
    partes = []

    ev = db.dataframe(
        """SELECT a.matricula, COALESCE(ev.nivel_final, ev.nivel_sugerido) AS nivel
           FROM evaluaciones ev JOIN evidencias e ON e.id = ev.evidencia_id
           JOIN alumnos a ON a.id = e.alumno_id JOIN asignaturas s ON s.id = e.asignatura_id
           WHERE s.ae_id = ?""",
        (rubrica["id"],),
    )
    partes.append(ev.assign(fuente="evidencias"))

    if "calificaciones" in fuentes:
        cfg = fuentes["calificaciones"]
        cal = db.dataframe(
            """SELECT a.matricula, s.nombre AS asignatura, c.calificacion
               FROM calificaciones c JOIN alumnos a ON a.id = c.alumno_id
               JOIN asignaturas s ON s.id = c.asignatura_id WHERE s.ae_id = ?""",
            (rubrica["id"],),
        )
        cal = cal[cal["asignatura"].isin(cfg["asignaturas"])]
        cal["nivel"] = cal["calificacion"].map(lambda x: nivel_por_calificacion(x, cfg["escala"]))
        partes.append(cal[["matricula", "nivel"]].assign(fuente="calificaciones"))

    if "ceneval" in fuentes:
        cfg = fuentes["ceneval"]
        cen = db.dataframe(
            "SELECT a.matricula, r.area, r.desempeno FROM resultados_ceneval r JOIN alumnos a ON a.id = r.alumno_id"
        )
        cen = cen[cen["area"].isin(cfg["areas"])]
        cen["nivel"] = cen["desempeno"].map(cfg["niveles"])
        partes.append(cen[["matricula", "nivel"]].assign(fuente="ceneval"))

    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["matricula", "nivel", "fuente"])


def resumen_adopcion(rubrica: dict) -> tuple[pd.DataFrame, float | None]:
    """Devuelve (tabla por fuente, índice combinado). El índice es None si no hay datos."""
    minimo = rubrica["nivel_minimo"]
    pesos = {k: v.get("peso", 0) for k, v in rubrica.get("fuentes", {"evidencias": {"peso": 1}}).items()}
    datos = niveles_por_fuente(rubrica)

    filas = []
    for fuente, peso in pesos.items():
        sub = datos[datos["fuente"] == fuente]
        filas.append({
            "fuente": fuente,
            "Fuente": ETIQUETAS.get(fuente, fuente),
            "Peso": peso,
            "Registros": len(sub),
            "Alumnos": sub["matricula"].nunique(),
            "Nivel promedio": sub["nivel"].mean() if len(sub) else None,
            "Cumplimiento": (sub["nivel"] >= minimo).mean() if len(sub) else None,
        })
    tabla = pd.DataFrame(filas)

    con_datos = tabla[tabla["Registros"] > 0]
    if con_datos.empty or con_datos["Peso"].sum() == 0:
        return tabla, None
    indice = (con_datos["Cumplimiento"] * con_datos["Peso"]).sum() / con_datos["Peso"].sum()
    return tabla, float(indice)
