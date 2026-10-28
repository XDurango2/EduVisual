import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "eduvisual.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS alumnos (
    id INTEGER PRIMARY KEY,
    matricula TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asignaturas (
    id INTEGER PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL,
    ae_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidencias (
    id INTEGER PRIMARY KEY,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id),
    asignatura_id INTEGER NOT NULL REFERENCES asignaturas(id),
    nombre_archivo TEXT NOT NULL,
    texto TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS evaluaciones (
    id INTEGER PRIMARY KEY,
    evidencia_id INTEGER NOT NULL REFERENCES evidencias(id) ON DELETE CASCADE,
    indicador_id TEXT NOT NULL,
    nivel_sugerido INTEGER NOT NULL,
    justificacion TEXT NOT NULL,
    citas TEXT NOT NULL DEFAULT '[]',
    motor TEXT NOT NULL,
    nivel_final INTEGER,
    revisado INTEGER NOT NULL DEFAULT 0,
    fecha_revision TEXT,
    UNIQUE (evidencia_id, indicador_id)
);
CREATE TABLE IF NOT EXISTS calificaciones (
    id INTEGER PRIMARY KEY,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id),
    asignatura_id INTEGER NOT NULL REFERENCES asignaturas(id),
    periodo TEXT NOT NULL,
    calificacion REAL NOT NULL,
    fecha_carga TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (alumno_id, asignatura_id, periodo)
);
CREATE TABLE IF NOT EXISTS resultados_ceneval (
    id INTEGER PRIMARY KEY,
    alumno_id INTEGER NOT NULL REFERENCES alumnos(id),
    examen TEXT NOT NULL,
    area TEXT NOT NULL,
    periodo TEXT NOT NULL,
    desempeno TEXT NOT NULL,
    puntaje INTEGER,
    fecha_carga TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (alumno_id, examen, area, periodo)
);
CREATE TABLE IF NOT EXISTS encuestas_empleadores (
    id INTEGER PRIMARY KEY,
    empleador TEXT NOT NULL,
    ae_id TEXT NOT NULL,
    periodo TEXT NOT NULL,
    respuesta REAL NOT NULL,
    fecha_carga TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (empleador, ae_id, periodo)
);
CREATE TABLE IF NOT EXISTS cargas (
    id INTEGER PRIMARY KEY,
    fuente TEXT NOT NULL,
    archivo TEXT NOT NULL,
    filas INTEGER NOT NULL,
    aceptadas INTEGER NOT NULL,
    rechazadas INTEGER NOT NULL,
    omitidas INTEGER NOT NULL,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def conexion():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with conexion() as con:
        con.executescript(SCHEMA)


def consulta(sql: str, params: tuple = ()) -> list[dict]:
    with conexion() as con:
        return [dict(fila) for fila in con.execute(sql, params).fetchall()]


def ejecutar(sql: str, params: tuple = ()) -> int:
    with conexion() as con:
        return con.execute(sql, params).lastrowid


def dataframe(sql: str, params: tuple = ()) -> pd.DataFrame:
    with conexion() as con:
        return pd.read_sql_query(sql, con, params=params)


def vaciar():
    with conexion() as con:
        con.executescript(
            "DROP TABLE IF EXISTS cargas; DROP TABLE IF EXISTS resultados_ceneval;"
            "DROP TABLE IF EXISTS encuestas_empleadores;"
            "DROP TABLE IF EXISTS calificaciones;"
            "DROP TABLE IF EXISTS evaluaciones; DROP TABLE IF EXISTS evidencias;"
            "DROP TABLE IF EXISTS asignaturas; DROP TABLE IF EXISTS alumnos;"
        )
        con.executescript(SCHEMA)


def obtener_o_crear_alumno(matricula: str, nombre: str) -> int:
    existente = consulta("SELECT id FROM alumnos WHERE matricula = ?", (matricula,))
    if existente:
        return existente[0]["id"]
    return ejecutar("INSERT INTO alumnos (matricula, nombre) VALUES (?, ?)", (matricula, nombre))


def obtener_o_crear_asignatura(nombre: str, ae_id: str) -> int:
    existente = consulta("SELECT id FROM asignaturas WHERE nombre = ?", (nombre,))
    if existente:
        return existente[0]["id"]
    return ejecutar("INSERT INTO asignaturas (nombre, ae_id) VALUES (?, ?)", (nombre, ae_id))


def guardar_evidencia(alumno_id: int, asignatura_id: int, nombre_archivo: str, texto: str) -> int:
    return ejecutar(
        "INSERT INTO evidencias (alumno_id, asignatura_id, nombre_archivo, texto) VALUES (?, ?, ?, ?)",
        (alumno_id, asignatura_id, nombre_archivo, texto),
    )


def guardar_evaluacion(evidencia_id: int, resultado: dict):
    """Guarda (o reemplaza) la sugerencia del motor y reinicia la revisión del docente."""
    import json

    ejecutar(
        """
        INSERT INTO evaluaciones (evidencia_id, indicador_id, nivel_sugerido, justificacion, citas, motor)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (evidencia_id, indicador_id) DO UPDATE SET
            nivel_sugerido = excluded.nivel_sugerido,
            justificacion = excluded.justificacion,
            citas = excluded.citas,
            motor = excluded.motor,
            nivel_final = NULL,
            revisado = 0,
            fecha_revision = NULL
        """,
        (
            evidencia_id,
            resultado["indicador_id"],
            resultado["nivel"],
            resultado["justificacion"],
            json.dumps(resultado["citas"], ensure_ascii=False),
            resultado["motor"],
        ),
    )


def guardar_revision(evaluacion_id: int, nivel_final: int):
    ejecutar(
        "UPDATE evaluaciones SET nivel_final = ?, revisado = 1, fecha_revision = CURRENT_TIMESTAMP WHERE id = ?",
        (nivel_final, evaluacion_id),
    )
