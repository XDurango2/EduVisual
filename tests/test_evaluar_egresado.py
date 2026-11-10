import sqlite3
from pathlib import Path

from streamlit.testing.v1 import AppTest

from core import db, seed

PAGINA = str(Path(__file__).resolve().parent.parent / "paginas" / "evaluar_egresado.py")
DOCUMENTO = (
    "Proyecto terminal. Se definió el problema, los requisitos y las restricciones con los usuarios. "
    "Se compararon alternativas con criterios ponderados y se justificó la selección. "
    "Se validó con pruebas, métricas e impacto."
)


def por_etiqueta(elementos, etiqueta):
    return next(e for e in elementos if e.label == etiqueta)


def test_migra_bases_sin_tipo_de_documento(tmp_path, monkeypatch):
    """Una base creada con la versión anterior recibe la columna sin perder sus evidencias."""
    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.executescript(
        "CREATE TABLE evidencias (id INTEGER PRIMARY KEY, alumno_id INTEGER NOT NULL, asignatura_id INTEGER NOT NULL,"
        " nombre_archivo TEXT NOT NULL, texto TEXT NOT NULL, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
        "INSERT INTO evidencias (alumno_id, asignatura_id, nombre_archivo, texto) VALUES (1, 1, 'a.txt', 'x');"
    )
    con.commit()
    con.close()
    monkeypatch.setattr(db, "DB_PATH", ruta)
    db.init_db()
    db.init_db()  # idempotente
    assert db.consulta("SELECT nombre_archivo, tipo_documento FROM evidencias") == [
        {"nombre_archivo": "a.txt", "tipo_documento": db.SIN_TIPO}
    ]


def test_sin_egresados_indica_donde_registrarlos():
    at = AppTest.from_file(PAGINA, default_timeout=60).run()
    assert not at.exception
    assert any("Carga de datos" in i.value for i in at.info)


def test_evaluar_y_confirmar_un_documento():
    seed.sembrar()
    alumno = db.consulta("SELECT id FROM alumnos WHERE matricula = 'A0101'")[0]["id"]
    antes = db.consulta("SELECT COUNT(*) AS n FROM evidencias")[0]["n"]

    at = AppTest.from_file(PAGINA, default_timeout=60).run()
    assert not at.exception
    por_etiqueta(at.selectbox, "Egresado").select(
        next(o for o in por_etiqueta(at.selectbox, "Egresado").options if o.startswith("A0101"))
    ).run()
    por_etiqueta(at.selectbox, "Tipo de documento").select("Reporte de prácticas profesionales").run()
    at.text_area[0].input(DOCUMENTO).run()
    por_etiqueta(at.button, "Evaluar documento").click().run()
    assert not at.exception

    nueva = db.consulta("SELECT id, alumno_id, tipo_documento FROM evidencias ORDER BY id DESC LIMIT 1")[0]
    assert db.consulta("SELECT COUNT(*) AS n FROM evidencias")[0]["n"] == antes + 1
    assert nueva["alumno_id"] == alumno and nueva["tipo_documento"] == "Reporte de prácticas profesionales"
    sugeridas = db.consulta("SELECT revisado FROM evaluaciones WHERE evidencia_id = ?", (nueva["id"],))
    assert len(sugeridas) == 3 and not any(e["revisado"] for e in sugeridas)

    # El paso 2 muestra el documento recién evaluado; el docente corrige un nivel y confirma.
    assert "Reporte de prácticas profesionales" in por_etiqueta(at.selectbox, "Documento").value["tipo_documento"]
    # Dentro de un formulario el valor se envía junto con el botón, en la misma ejecución.
    at.select_slider[0].set_value(1)
    por_etiqueta(at.button, "Confirmar evaluación").click().run()
    assert not at.exception
    finales = db.consulta(
        "SELECT indicador_id, nivel_final, revisado FROM evaluaciones WHERE evidencia_id = ? ORDER BY indicador_id",
        (nueva["id"],),
    )
    assert all(f["revisado"] == 1 for f in finales)
    assert finales[0]["nivel_final"] == 1
    assert any("Evaluación confirmada" in s.value for s in at.success)


def test_documento_vacio_no_se_guarda():
    seed.sembrar()
    antes = db.consulta("SELECT COUNT(*) AS n FROM evidencias")[0]["n"]
    at = AppTest.from_file(PAGINA, default_timeout=60).run()
    por_etiqueta(at.button, "Evaluar documento").click().run()
    assert any("vacío" in e.value for e in at.error)
    assert db.consulta("SELECT COUNT(*) AS n FROM evidencias")[0]["n"] == antes


def test_app_inicia_en_la_pagina_de_inicio():
    at = AppTest.from_file(str(Path(PAGINA).parent.parent / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "EduVisual"
