"""Actividades calificadas: la fuente principal de evidencias de un Atributo de Egreso.

Una actividad es una tarea de una unidad de aprendizaje que evalúa un AE y que el docente YA calificó
(en Google Classroom o en papel). EduVisual no la vuelve a calificar: convierte la calificación (0-100) al
nivel 1-4 de la rúbrica con la escala `fuentes.evidencias.escala` (o, si no existe, la de calificaciones).

Flujo, igual que el resto de las cargas: un conector entrega una `Lectura` -> validar() -> importar().
La captura manual usa el mismo camino con una sola entrega.

Minimización de datos: sólo se guardan las actividades que el docente marca como evidencia del AE.
"""
import json

from core import db
from core.adopcion import nivel_por_calificacion
from core.conectores import Lectura
from core.importacion import Validacion, _clave, _registrar

ORIGEN_MANUAL = "manual"
ETIQUETA_ORIGEN = {"classroom": "Google Classroom", ORIGEN_MANUAL: "Captura manual", db.ORIGEN_MOTOR: "Motor (documento)"}
ESCALA_POR_DEFECTO = [{"desde": 0, "nivel": 1}, {"desde": 60, "nivel": 2}, {"desde": 80, "nivel": 3}, {"desde": 90, "nivel": 4}]


def escala(rubrica: dict) -> list[dict]:
    """Tramos calificación -> nivel para las actividades de este AE."""
    fuentes = rubrica.get("fuentes", {})
    return (fuentes.get("evidencias", {}).get("escala")
            or fuentes.get("calificaciones", {}).get("escala")
            or ESCALA_POR_DEFECTO)


def nivel(calificacion: float, rubrica: dict) -> int:
    return nivel_por_calificacion(calificacion, escala(rubrica))


def validar(lectura: Lectura, seleccion: dict[str, list[str]], archivo: str = "") -> Validacion:
    """Valida las entregas de las actividades elegidas. `seleccion`: actividad -> ids de los indicadores que evalúa.

    Cada alumno se identifica por matrícula (captura manual), por correo o por nombre; si no existe se registra
    con la parte local de su correo como matrícula. Las entregas sin calificar se omiten."""
    v = Validacion(fuente=f"actividades ({lectura.origen})", archivo=archivo)
    entregas = [e for e in lectura.entregas if e["actividad"] in seleccion]
    v.filas = len(entregas)
    if not seleccion:
        v.error_archivo = "Elige al menos una actividad."
        return v
    if not entregas:
        v.error_archivo = "Las actividades elegidas no tienen entregas."
        return v

    alumnos = db.consulta("SELECT id, matricula, nombre, correo FROM alumnos")
    por_matricula = {a["matricula"]: a for a in alumnos}
    por_correo = {a["correo"].lower(): a for a in alumnos if a["correo"]}
    por_nombre = {_clave(a["nombre"]): a for a in alumnos}

    vistas = set()
    for e in entregas:
        ref = e.get("matricula") or e.get("correo") or e.get("nombre")
        base = {"fila": e["fila"], "alumno": ref, "actividad": e["actividad"]}
        if not seleccion[e["actividad"]]:
            v.rechazos.append({**base, "motivo": "la actividad no tiene indicadores asignados"})
            continue
        valor = str(e["valor"]).strip()
        if not valor:
            v.omitidas.append({**base, "motivo": "entrega sin calificar (no se almacena)"})
            continue
        try:
            puntos = float(valor.replace(",", "."))
        except ValueError:
            v.rechazos.append({**base, "motivo": f"calificación '{valor}' no es numérica"})
            continue
        if puntos < 0:
            v.rechazos.append({**base, "motivo": f"calificación {puntos:g} negativa"})
            continue
        calificacion = round(min(puntos / e["puntos"] * 100, 100), 1)  # los puntos extra no pasan de 100

        alumno = (por_matricula.get(e.get("matricula", "")) or por_correo.get(e.get("correo", ""))
                  or por_nombre.get(_clave(e.get("nombre", ""))))
        if alumno:
            matricula, nombre = alumno["matricula"], alumno["nombre"]
        elif e.get("matricula") and e.get("nombre"):
            matricula, nombre = e["matricula"], e["nombre"]
        elif e.get("correo") and e.get("nombre"):
            matricula, nombre = e["correo"].split("@")[0], e["nombre"]
        else:
            v.rechazos.append({**base, "motivo": "no se pudo identificar al alumno (falta el correo o el nombre)"})
            continue

        llave = (matricula, _clave(e["actividad"]))
        if llave in vistas:
            v.rechazos.append({**base, "motivo": "entrega duplicada (mismo alumno y actividad)"})
            continue
        vistas.add(llave)
        v.validas.append({
            "matricula": matricula, "nombre": nombre, "correo": e.get("correo", ""), "alumno_nuevo": alumno is None,
            "actividad": e["actividad"], "calificacion": calificacion, "indicadores": list(seleccion[e["actividad"]]),
            "archivo": e.get("archivo", ""), "texto": e.get("texto", ""),
        })
    return v


def importar(v: Validacion, rubrica: dict, asignatura: str, origen: str) -> int:
    """Guarda las entregas válidas como evidencias con su nivel por indicador y registra la carga.
    Volver a importar la misma actividad de un alumno la reemplaza."""
    if v.error_archivo:
        raise ValueError(v.error_archivo)
    with db.conexion() as con:
        fila = con.execute("SELECT id FROM asignaturas WHERE nombre = ?", (asignatura,)).fetchone()
        asignatura_id = fila["id"] if fila else con.execute(
            "INSERT INTO asignaturas (nombre, ae_id) VALUES (?, ?)", (asignatura, rubrica["id"])).lastrowid

        for f in v.validas:
            alumno = con.execute("SELECT id, correo FROM alumnos WHERE matricula = ?", (f["matricula"],)).fetchone()
            if alumno:
                alumno_id = alumno["id"]
                if f["correo"] and not alumno["correo"]:
                    con.execute("UPDATE alumnos SET correo = ? WHERE id = ?", (f["correo"], alumno_id))
            else:
                alumno_id = con.execute("INSERT INTO alumnos (matricula, nombre, correo) VALUES (?, ?, ?)",
                                        (f["matricula"], f["nombre"], f["correo"] or None)).lastrowid

            con.execute(
                "DELETE FROM evidencias WHERE alumno_id = ? AND asignatura_id = ? AND actividad = ? AND origen != ?",
                (alumno_id, asignatura_id, f["actividad"], db.ORIGEN_MOTOR),
            )
            evidencia_id = con.execute(
                """INSERT INTO evidencias (alumno_id, asignatura_id, nombre_archivo, texto, tipo_documento, origen,
                                           actividad, calificacion) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (alumno_id, asignatura_id, f["archivo"] or f["actividad"], f["texto"], db.TIPO_ACTIVIDAD, origen,
                 f["actividad"], f["calificacion"]),
            ).lastrowid
            n = nivel(f["calificacion"], rubrica)
            justificacion = (f"Calificación {f['calificacion']:g}/100 asignada por el docente "
                             f"({ETIQUETA_ORIGEN.get(origen, origen)}); equivale al nivel {n} · {rubrica['niveles'][str(n)]}.")
            for indicador in f["indicadores"]:
                con.execute(
                    """INSERT INTO evaluaciones (evidencia_id, indicador_id, nivel_sugerido, justificacion, citas, motor,
                                                 nivel_final, revisado, fecha_revision)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)""",
                    (evidencia_id, indicador, n, justificacion, json.dumps([]), db.MOTOR_CALIFICACION, n),
                )
        _registrar(con, v)
    return len(v.validas)


def registrar_manual(rubrica: dict, asignatura: str, actividad: str, matricula: str, nombre: str, calificacion: float,
                     indicadores: list[str], archivo: str = "", texto: str = "") -> Validacion:
    """Captura manual de una actividad calificada (un alumno). Devuelve la validación; si no tiene rechazos, ya se guardó."""
    lectura = Lectura(origen=ORIGEN_MANUAL, actividades=[{"nombre": actividad, "puntos": 100.0, "fecha": ""}], entregas=[{
        "fila": 1, "nombre": nombre, "correo": "", "matricula": matricula, "actividad": actividad,
        "valor": str(calificacion), "puntos": 100.0, "archivo": archivo, "texto": texto,
    }])
    v = validar(lectura, {actividad: indicadores}, archivo or "captura manual")
    if not v.error_archivo and v.validas:
        importar(v, rubrica, asignatura, ORIGEN_MANUAL)
    return v


def registradas(rubrica: dict):
    """Resumen de las actividades guardadas para el AE: una fila por actividad y unidad de aprendizaje."""
    df = db.dataframe(
        """SELECT e.actividad AS Actividad, s.nombre AS "Unidad de aprendizaje", e.origen, e.alumno_id, e.calificacion,
                  (SELECT group_concat(indicador_id, ', ') FROM evaluaciones WHERE evidencia_id = e.id) AS Indicadores
           FROM evidencias e JOIN asignaturas s ON s.id = e.asignatura_id
           WHERE s.ae_id = ? AND e.origen != ?""",
        (rubrica["id"], db.ORIGEN_MOTOR),
    )
    if df.empty:
        return df
    minimo = rubrica["nivel_minimo"]
    df["nivel"] = df["calificacion"].map(lambda c: nivel(c, rubrica))
    df["Origen"] = df["origen"].map(lambda o: ETIQUETA_ORIGEN.get(o, o))
    return df.groupby(["Actividad", "Unidad de aprendizaje", "Origen", "Indicadores"], as_index=False).agg(
        Alumnos=("alumno_id", "nunique"), **{"Calificación promedio": ("calificacion", "mean")},
        **{f"% con nivel ≥ {minimo}": ("nivel", lambda n: (n >= minimo).mean())},
    ).round(2)


def eliminar(rubrica: dict, asignatura: str, actividad: str) -> int:
    """Borra una actividad calificada (todas sus entregas) de una unidad de aprendizaje."""
    with db.conexion() as con:
        return con.execute(
            """DELETE FROM evidencias WHERE actividad = ? AND origen != ? AND asignatura_id IN
               (SELECT id FROM asignaturas WHERE nombre = ? AND ae_id = ?)""",
            (actividad, db.ORIGEN_MOTOR, asignatura, rubrica["id"]),
        ).rowcount
