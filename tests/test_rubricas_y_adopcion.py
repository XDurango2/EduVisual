import copy

import pandas as pd

from core import db, importacion
from core.adopcion import nivel_por_calificacion, resumen_adopcion
from core.rubricas import validar_rubrica


def test_rubrica_de_ejemplo_es_valida(rubricas):
    assert validar_rubrica(rubricas["AE-03"]) == []


def test_validador_detecta_errores(rubricas):
    r = copy.deepcopy(rubricas["AE-03"])
    r["nivel_minimo"] = 9
    r["fuentes"]["ceneval"]["peso"] = 0.9
    r["indicadores"][0]["niveles"].pop("4")
    r["validacion"]["estado"] = "aprobadísima"
    errores = " | ".join(validar_rubrica(r))
    assert "nivel_minimo" in errores
    assert "deben sumar 1" in errores
    assert "niveles 1 a 4" in errores
    assert "validacion.estado" in errores


def test_validador_detecta_campos_faltantes():
    assert "falta el campo 'indicadores'" in validar_rubrica({"id": "X"})


def test_escala_de_calificaciones(rubricas):
    escala = rubricas["AE-03"]["fuentes"]["calificaciones"]["escala"]
    assert [nivel_por_calificacion(x, escala) for x in (0, 59.9, 60, 79.9, 80, 89.9, 90, 100)] == [1, 1, 2, 2, 3, 3, 4, 4]


def test_indice_sin_datos_es_none(rubricas):
    tabla, indice = resumen_adopcion(rubricas["AE-03"])
    assert indice is None and (tabla["Registros"] == 0).all()


def test_indice_renormaliza_pesos_entre_fuentes_con_datos(rubricas):
    r = rubricas["AE-03"]
    cal = pd.DataFrame(
        [["1", "Ana", "Ingeniería de Software", "2026-1", "95"], ["2", "Luis", "Ingeniería de Software", "2026-1", "65"]],
        columns=importacion.COLUMNAS["calificaciones"],
    ).astype(str)
    importacion.importar(importacion.validar_calificaciones(cal, {r["id"]: r}))
    tabla, indice = resumen_adopcion(r)
    # Sólo hay calificaciones: 1 de 2 alumnos con nivel >= 3, así que el índice es 50 %.
    assert indice == 0.5
    assert tabla.set_index("fuente").loc["calificaciones", "Registros"] == 2


def test_indice_combina_las_tres_fuentes(rubricas):
    from core import seed

    seed.sembrar()  # escribe en la base temporal de la prueba
    tabla, indice = resumen_adopcion(rubricas["AE-03"])
    esperado = (tabla["Cumplimiento"] * tabla["Peso"]).sum() / tabla["Peso"].sum()
    assert (tabla["Registros"] > 0).all()
    assert abs(indice - esperado) < 1e-9
    assert db.consulta("SELECT COUNT(*) AS n FROM cargas")[0]["n"] == 2
