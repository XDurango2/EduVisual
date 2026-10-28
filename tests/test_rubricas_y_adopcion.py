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


def test_indice_combina_las_cuatro_fuentes(rubricas):
    from core import seed

    seed.sembrar()  # escribe en la base temporal de la prueba
    tabla, indice = resumen_adopcion(rubricas["AE-03"])
    esperado = (tabla["Cumplimiento"] * tabla["Peso"]).sum() / tabla["Peso"].sum()
    assert (tabla["Registros"] > 0).all()
    assert abs(indice - esperado) < 1e-9
    assert set(tabla["fuente"]) == {"evidencias", "calificaciones", "ceneval", "encuestas"}
    assert db.consulta("SELECT COUNT(*) AS n FROM cargas")[0]["n"] == 3


def test_resumen_y_reporte_consolidado(rubricas):
    import io

    from core import seed
    from core.reportes import libro_excel
    from core.resumen import resumen_preliminar

    seed.sembrar()
    r = rubricas["AE-03"]
    assert "índice de adopción combinado" in resumen_preliminar(r)
    hojas = pd.ExcelFile(io.BytesIO(libro_excel(r))).sheet_names
    assert {"Resumen", "Adopción por fuente", "Por alumno", "Encuestas"} <= set(hojas)


def test_resumen_sin_datos(rubricas):
    from core.resumen import resumen_preliminar

    assert "Aún no hay datos" in resumen_preliminar(rubricas["AE-03"])


def test_reporte_pdf(rubricas):
    from core import seed
    from core.reportes import pdf

    seed.sembrar()
    assert pdf(rubricas["AE-03"]).startswith(b"%PDF")


def test_equivalencia_oficial_coherente_con_nivel_minimo(rubricas):
    from core import reportes

    r = rubricas["AE-03"]
    eq = reportes.equivalencia(r)
    assert eq == {1: "NS", 2: "NS", 3: "SA", 4: "SO"}
    # "Cumple" en el formato oficial (SA o SO) equivale a nivel >= nivel_minimo.
    assert all((eq[n] != "NS") == (n >= r["nivel_minimo"]) for n in eq)


def test_validador_rechaza_equivalencia_invalida(rubricas):
    r = copy.deepcopy(rubricas["AE-03"])
    r["formato_oficial"]["equivalencia"]["2"] = "BUENO"
    assert "formato_oficial.equivalencia" in " | ".join(validar_rubrica(r))


def test_cedula_distribucion_y_pdf(rubricas):
    from core import reportes, seed

    seed.sembrar()
    r = rubricas["AE-03"]
    asignatura = db.consulta("SELECT nombre FROM asignaturas")[0]["nombre"]
    cedula = reportes.cedula_ua(r, asignatura)
    desglose = cedula["Desglose"]
    # Cada alumno tiene exactamente una X por indicador.
    for ind in r["indicadores"]:
        assert (desglose[[f"{ind['id']} {g}" for g in reportes.GRADOS]] == "X").sum(axis=1).eq(1).all()
    assert len(cedula["Distribución"]) == len(r["indicadores"])
    assert reportes.cedula_pdf(r, asignatura, {"clave": "1"}).startswith(b"%PDF")
