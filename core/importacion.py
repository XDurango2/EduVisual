"""Integración de fuentes externas: calificaciones (RF-001) y resultados CENEVAL (RF-002).

Flujo: leer_tabla() -> validar_*() -> importar_*(). La validación es fila por fila y no escribe nada;
la importación guarda sólo las filas válidas en una transacción y registra la carga en la bitácora.

Minimización de datos (Plan de Manejo de la Privacidad): sólo se almacenan calificaciones de asignaturas y
resultados de áreas CENEVAL vinculadas a algún Atributo de Egreso. Las demás filas se omiten sin guardarse.
"""
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from core import db

META_RECHAZO = 0.02  # Plan de Calidad: menos de 2% de registros rechazados por carga.
PERIODO_RE = re.compile(r"^\d{4}-[1-3]$")  # Formato UABC: 2026-1, 2026-2 (3 = intersemestral).
PUNTAJE_MIN, PUNTAJE_MAX = 700, 1300  # Escala del Índice CENEVAL.

COLUMNAS = {
    "calificaciones": ["matricula", "nombre", "asignatura", "periodo", "calificacion"],
    "ceneval": ["matricula", "nombre", "examen", "area", "periodo", "desempeno", "puntaje"],
}
OBLIGATORIAS = {
    "calificaciones": ["matricula", "asignatura", "periodo", "calificacion"],
    "ceneval": ["matricula", "examen", "area", "periodo", "desempeno"],
}
DESEMPENO = {
    "ans": "ANS", "aun no satisfactorio": "ANS",
    "ds": "DS", "satisfactorio": "DS", "desempeno satisfactorio": "DS",
    "dss": "DSS", "sobresaliente": "DSS", "desempeno sobresaliente": "DSS",
}


@dataclass
class Validacion:
    fuente: str
    archivo: str
    filas: int = 0
    validas: list[dict] = field(default_factory=list)
    rechazos: list[dict] = field(default_factory=list)  # {"fila", "motivo"}
    omitidas: list[dict] = field(default_factory=list)  # {"fila", "motivo"}
    error_archivo: str | None = None

    @property
    def tasa_rechazo(self) -> float:
        return len(self.rechazos) / self.filas if self.filas else 0.0

    @property
    def cumple_meta(self) -> bool:
        return self.error_archivo is None and self.tasa_rechazo < META_RECHAZO


def _clave(texto) -> str:
    """Normaliza para comparar: minúsculas, sin acentos ni espacios extra."""
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _texto(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)  # Excel convierte matrículas numéricas en 1234567.0
    return str(valor).strip()


def leer_tabla(nombre: str, contenido: bytes) -> pd.DataFrame:
    """Lee CSV o Excel como texto y normaliza los encabezados (sin acentos, minúsculas)."""
    ext = Path(nombre).suffix.lower()
    if ext == ".csv":
        for codificacion in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(contenido), dtype=str, encoding=codificacion, keep_default_na=False)
                break
            except UnicodeDecodeError:
                continue
    elif ext in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(io.BytesIO(contenido), dtype=str, keep_default_na=False)
        except ImportError:
            raise ValueError("Para leer Excel instala openpyxl: pip install openpyxl")
    else:
        raise ValueError(f"Formato no soportado: {ext or 'sin extensión'}. Usa CSV o Excel (.xlsx).")
    df.columns = [_clave(c).replace(" ", "_") for c in df.columns]
    return df


def _validar_alumno(fila: dict, alumnos: dict[str, str]) -> str | None:
    if not fila["matricula"]:
        return "falta la matrícula"
    if fila["matricula"] not in alumnos and not fila.get("nombre"):
        return "alumno nuevo sin nombre"
    return None


def _base(fuente: str, df: pd.DataFrame, archivo: str) -> Validacion:
    v = Validacion(fuente=fuente, archivo=archivo, filas=len(df))
    faltantes = [c for c in OBLIGATORIAS[fuente] if c not in df.columns]
    if faltantes:
        v.error_archivo = f"Faltan columnas obligatorias: {', '.join(faltantes)}"
    elif df.empty:
        v.error_archivo = "El archivo no tiene filas de datos."
    return v


def validar_calificaciones(df: pd.DataFrame, rubricas: dict[str, dict], archivo: str = "") -> Validacion:
    v = _base("calificaciones", df, archivo)
    if v.error_archivo:
        return v

    vinculadas = {}  # asignatura normalizada -> (nombre oficial, ae_id)
    for r in rubricas.values():
        for a in r.get("fuentes", {}).get("calificaciones", {}).get("asignaturas", []):
            vinculadas[_clave(a)] = (a, r["id"])
    alumnos = {a["matricula"]: a["nombre"] for a in db.consulta("SELECT matricula, nombre FROM alumnos")}

    vistas = set()
    for i, registro in enumerate(df.to_dict("records")):
        n = i + 2  # fila 1 = encabezados, igual que en Excel
        fila = {c: _texto(registro.get(c)) for c in COLUMNAS["calificaciones"]}

        motivo = _validar_alumno(fila, alumnos)
        if not motivo and not fila["asignatura"]:
            motivo = "falta la asignatura"
        if not motivo and not PERIODO_RE.match(fila["periodo"]):
            motivo = f"periodo '{fila['periodo']}' inválido (formato AAAA-N, ej. 2026-1)"
        if not motivo:
            try:
                calif = float(fila["calificacion"].replace(",", "."))
                if not 0 <= calif <= 100:
                    motivo = f"calificación {calif:g} fuera del rango 0-100"
            except ValueError:
                motivo = f"calificación '{fila['calificacion']}' no es numérica"
        if motivo:
            v.rechazos.append({"fila": n, "matricula": fila["matricula"], "motivo": motivo})
            continue

        if _clave(fila["asignatura"]) not in vinculadas:
            v.omitidas.append({"fila": n, "matricula": fila["matricula"],
                               "motivo": f"'{fila['asignatura']}' no tributa a ningún AE (no se almacena)"})
            continue

        asignatura, ae_id = vinculadas[_clave(fila["asignatura"])]
        llave = (fila["matricula"], _clave(asignatura), fila["periodo"])
        if llave in vistas:
            v.rechazos.append({"fila": n, "matricula": fila["matricula"],
                               "motivo": "registro duplicado en el archivo (misma matrícula, asignatura y periodo)"})
            continue
        vistas.add(llave)
        v.validas.append({"matricula": fila["matricula"], "nombre": fila["nombre"], "asignatura": asignatura,
                          "ae_id": ae_id, "periodo": fila["periodo"], "calificacion": calif})
    return v


def validar_ceneval(df: pd.DataFrame, rubricas: dict[str, dict], archivo: str = "") -> Validacion:
    v = _base("ceneval", df, archivo)
    if v.error_archivo:
        return v

    vinculadas = {}  # área normalizada -> nombre oficial
    for r in rubricas.values():
        for a in r.get("fuentes", {}).get("ceneval", {}).get("areas", []):
            vinculadas[_clave(a)] = a
    alumnos = {a["matricula"]: a["nombre"] for a in db.consulta("SELECT matricula, nombre FROM alumnos")}

    vistas = set()
    for i, registro in enumerate(df.to_dict("records")):
        n = i + 2
        fila = {c: _texto(registro.get(c)) for c in COLUMNAS["ceneval"]}

        motivo = _validar_alumno(fila, alumnos)
        if not motivo and not fila["examen"]:
            motivo = "falta el examen"
        if not motivo and not fila["area"]:
            motivo = "falta el área"
        if not motivo and not PERIODO_RE.match(fila["periodo"]):
            motivo = f"periodo '{fila['periodo']}' inválido (formato AAAA-N, ej. 2026-1)"
        desempeno = DESEMPENO.get(_clave(fila["desempeno"]))
        if not motivo and not desempeno:
            motivo = f"desempeño '{fila['desempeno']}' no reconocido (usa ANS, DS o DSS)"
        puntaje = None
        if not motivo and fila["puntaje"]:
            try:
                puntaje = int(float(fila["puntaje"]))
                if not PUNTAJE_MIN <= puntaje <= PUNTAJE_MAX:
                    motivo = f"puntaje {puntaje} fuera de la escala {PUNTAJE_MIN}-{PUNTAJE_MAX}"
            except ValueError:
                motivo = f"puntaje '{fila['puntaje']}' no es numérico"
        if motivo:
            v.rechazos.append({"fila": n, "matricula": fila["matricula"], "motivo": motivo})
            continue

        if _clave(fila["area"]) not in vinculadas:
            v.omitidas.append({"fila": n, "matricula": fila["matricula"],
                               "motivo": f"el área '{fila['area']}' no tributa a ningún AE (no se almacena)"})
            continue

        area = vinculadas[_clave(fila["area"])]
        llave = (fila["matricula"], _clave(fila["examen"]), _clave(area), fila["periodo"])
        if llave in vistas:
            v.rechazos.append({"fila": n, "matricula": fila["matricula"],
                               "motivo": "registro duplicado en el archivo (misma matrícula, examen, área y periodo)"})
            continue
        vistas.add(llave)
        v.validas.append({"matricula": fila["matricula"], "nombre": fila["nombre"], "examen": fila["examen"],
                          "area": area, "periodo": fila["periodo"], "desempeno": desempeno, "puntaje": puntaje})
    return v


def _id_alumno(con, matricula: str, nombre: str) -> int:
    fila = con.execute("SELECT id FROM alumnos WHERE matricula = ?", (matricula,)).fetchone()
    if fila:
        return fila["id"]
    return con.execute("INSERT INTO alumnos (matricula, nombre) VALUES (?, ?)", (matricula, nombre)).lastrowid


def _id_asignatura(con, nombre: str, ae_id: str) -> int:
    fila = con.execute("SELECT id FROM asignaturas WHERE nombre = ?", (nombre,)).fetchone()
    if fila:
        return fila["id"]
    return con.execute("INSERT INTO asignaturas (nombre, ae_id) VALUES (?, ?)", (nombre, ae_id)).lastrowid


def _registrar(con, v: Validacion):
    con.execute(
        "INSERT INTO cargas (fuente, archivo, filas, aceptadas, rechazadas, omitidas) VALUES (?, ?, ?, ?, ?, ?)",
        (v.fuente, v.archivo, v.filas, len(v.validas), len(v.rechazos), len(v.omitidas)),
    )


def importar(v: Validacion) -> int:
    """Guarda las filas válidas en una sola transacción (re-importar actualiza) y registra la carga."""
    if v.error_archivo:
        raise ValueError(v.error_archivo)
    with db.conexion() as con:
        for f in v.validas:
            alumno_id = _id_alumno(con, f["matricula"], f["nombre"])
            if v.fuente == "calificaciones":
                con.execute(
                    """INSERT INTO calificaciones (alumno_id, asignatura_id, periodo, calificacion)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT (alumno_id, asignatura_id, periodo) DO UPDATE SET
                           calificacion = excluded.calificacion, fecha_carga = CURRENT_TIMESTAMP""",
                    (alumno_id, _id_asignatura(con, f["asignatura"], f["ae_id"]), f["periodo"], f["calificacion"]),
                )
            else:
                con.execute(
                    """INSERT INTO resultados_ceneval (alumno_id, examen, area, periodo, desempeno, puntaje)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT (alumno_id, examen, area, periodo) DO UPDATE SET
                           desempeno = excluded.desempeno, puntaje = excluded.puntaje,
                           fecha_carga = CURRENT_TIMESTAMP""",
                    (alumno_id, f["examen"], f["area"], f["periodo"], f["desempeno"], f["puntaje"]),
                )
        _registrar(con, v)
    return len(v.validas)


def plantilla_csv(fuente: str) -> bytes:
    """CSV de ejemplo con los encabezados esperados."""
    ejemplos = {
        "calificaciones": [["1234567", "Nombre Apellido", "Ingeniería de Software", "2026-1", "87"]],
        "ceneval": [["1234567", "Nombre Apellido", "EGEL (ejemplo)", "Diseño de soluciones de software (ejemplo)",
                     "2026-1", "DS", "1080"]],
    }
    df = pd.DataFrame(ejemplos[fuente], columns=COLUMNAS[fuente])
    return df.to_csv(index=False).encode("utf-8-sig")
