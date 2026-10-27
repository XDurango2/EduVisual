import pandas as pd
import pytest

from core import db, importacion
from core.importacion import leer_tabla, validar_calificaciones, validar_ceneval

ASIG = "Ingeniería de Software"
AREA = "Diseño de soluciones de software (ejemplo)"


def tabla_cal(filas):
    return pd.DataFrame(filas, columns=importacion.COLUMNAS["calificaciones"]).astype(str)


def tabla_cen(filas):
    return pd.DataFrame(filas, columns=importacion.COLUMNAS["ceneval"]).astype(str)


# ------------------------------------------------------------------ lectura de archivos
def test_lee_csv_con_encabezados_con_acentos_y_bom():
    contenido = "﻿Matrícula,Nombre,Asignatura,Periodo,Calificación\n1234567,Ana,X,2026-1,90\n".encode("utf-8")
    df = leer_tabla("datos.csv", contenido)
    assert list(df.columns) == ["matricula", "nombre", "asignatura", "periodo", "calificacion"]
    assert df.iloc[0]["matricula"] == "1234567"


def test_lee_csv_en_latin1():
    contenido = "matricula,nombre,asignatura,periodo,calificacion\n1,José,X,2026-1,90\n".encode("latin-1")
    assert leer_tabla("datos.csv", contenido).iloc[0]["nombre"] == "José"


def test_rechaza_formato_no_soportado():
    with pytest.raises(ValueError, match="Formato no soportado"):
        leer_tabla("datos.txt", b"x")


def test_lee_excel(tmp_path):
    ruta = tmp_path / "datos.xlsx"
    tabla_cal([["1234567", "Ana", ASIG, "2026-1", "90"]]).to_excel(ruta, index=False)
    assert leer_tabla("datos.xlsx", ruta.read_bytes()).iloc[0]["asignatura"] == ASIG


# ------------------------------------------------------------------ RF-001 calificaciones
def test_calificaciones_validas_se_importan(rubricas):
    v = validar_calificaciones(tabla_cal([["1001", "Ana", ASIG, "2026-1", "88.5"]]), rubricas, "a.csv")
    assert len(v.validas) == 1 and not v.rechazos and v.cumple_meta
    assert importacion.importar(v) == 1
    fila = db.consulta("SELECT calificacion, periodo FROM calificaciones")[0]
    assert fila == {"calificacion": 88.5, "periodo": "2026-1"}


@pytest.mark.parametrize("fila, motivo", [
    (["", "Ana", ASIG, "2026-1", "90"], "falta la matrícula"),
    (["1001", "", ASIG, "2026-1", "90"], "alumno nuevo sin nombre"),
    (["1001", "Ana", "", "2026-1", "90"], "falta la asignatura"),
    (["1001", "Ana", ASIG, "2026/1", "90"], "periodo"),
    (["1001", "Ana", ASIG, "2026-1", "105"], "fuera del rango"),
    (["1001", "Ana", ASIG, "2026-1", "noventa"], "no es numérica"),
])
def test_calificaciones_invalidas_se_rechazan_con_motivo(rubricas, fila, motivo):
    v = validar_calificaciones(tabla_cal([fila]), rubricas)
    assert not v.validas
    assert motivo in v.rechazos[0]["motivo"]
    assert v.rechazos[0]["fila"] == 2  # fila 1 son los encabezados


def test_asignatura_no_vinculada_se_omite_y_no_cuenta_como_rechazo(rubricas):
    v = validar_calificaciones(tabla_cal([["1001", "Ana", "Cálculo Diferencial", "2026-1", "90"]]), rubricas)
    assert len(v.omitidas) == 1 and not v.rechazos and not v.validas


def test_asignatura_se_compara_sin_acentos_ni_mayusculas(rubricas):
    v = validar_calificaciones(tabla_cal([["1001", "Ana", "INGENIERIA DE SOFTWARE", "2026-1", "90"]]), rubricas)
    assert v.validas[0]["asignatura"] == ASIG


def test_duplicado_en_el_archivo_se_rechaza(rubricas):
    fila = ["1001", "Ana", ASIG, "2026-1", "90"]
    v = validar_calificaciones(tabla_cal([fila, fila]), rubricas)
    assert len(v.validas) == 1 and "duplicado" in v.rechazos[0]["motivo"]


def test_reimportar_actualiza_en_lugar_de_duplicar(rubricas):
    importacion.importar(validar_calificaciones(tabla_cal([["1001", "Ana", ASIG, "2026-1", "70"]]), rubricas))
    importacion.importar(validar_calificaciones(tabla_cal([["1001", "", ASIG, "2026-1", "95"]]), rubricas))
    assert db.consulta("SELECT calificacion FROM calificaciones") == [{"calificacion": 95.0}]
    assert db.consulta("SELECT COUNT(*) AS n FROM cargas")[0]["n"] == 2


def test_columnas_faltantes_invalidan_el_archivo(rubricas):
    v = validar_calificaciones(pd.DataFrame({"matricula": ["1"]}), rubricas)
    assert "Faltan columnas obligatorias" in v.error_archivo
    with pytest.raises(ValueError):
        importacion.importar(v)


def test_meta_de_rechazo_de_2_por_ciento(rubricas):
    buenas = [[str(1000 + i), "A", ASIG, "2026-1", "80"] for i in range(99)]
    v = validar_calificaciones(tabla_cal(buenas + [["", "A", ASIG, "2026-1", "80"]]), rubricas)
    assert v.tasa_rechazo == pytest.approx(0.01) and v.cumple_meta
    v = validar_calificaciones(tabla_cal(buenas[:49] + [["", "A", ASIG, "2026-1", "80"]]), rubricas)
    assert v.tasa_rechazo == pytest.approx(0.02) and not v.cumple_meta


# ------------------------------------------------------------------ RF-002 CENEVAL
def test_ceneval_valido_normaliza_desempeno(rubricas):
    v = validar_ceneval(tabla_cen([["1001", "Ana", "EGEL", AREA, "2026-1", "Desempeño sobresaliente", "1180"]]), rubricas)
    assert v.validas[0]["desempeno"] == "DSS" and v.validas[0]["puntaje"] == 1180
    importacion.importar(v)
    assert db.consulta("SELECT desempeno, puntaje FROM resultados_ceneval") == [{"desempeno": "DSS", "puntaje": 1180}]


def test_ceneval_puntaje_es_opcional(rubricas):
    v = validar_ceneval(tabla_cen([["1001", "Ana", "EGEL", AREA, "2026-1", "DS", ""]]), rubricas)
    assert v.validas[0]["puntaje"] is None


@pytest.mark.parametrize("fila, motivo", [
    (["1001", "Ana", "", AREA, "2026-1", "DS", ""], "falta el examen"),
    (["1001", "Ana", "EGEL", "", "2026-1", "DS", ""], "falta el área"),
    (["1001", "Ana", "EGEL", AREA, "2026-1", "Excelente", ""], "no reconocido"),
    (["1001", "Ana", "EGEL", AREA, "2026-1", "DS", "1500"], "fuera de la escala"),
    (["1001", "Ana", "EGEL", AREA, "2026-1", "DS", "mil"], "no es numérico"),
])
def test_ceneval_invalido_se_rechaza(rubricas, fila, motivo):
    v = validar_ceneval(tabla_cen([fila]), rubricas)
    assert motivo in v.rechazos[0]["motivo"]


def test_ceneval_area_no_vinculada_se_omite(rubricas):
    v = validar_ceneval(tabla_cen([["1001", "Ana", "EGEL", "Otra área", "2026-1", "DS", ""]]), rubricas)
    assert len(v.omitidas) == 1 and not v.validas


def test_plantillas_tienen_los_encabezados_esperados():
    for fuente in ("calificaciones", "ceneval"):
        df = leer_tabla("p.csv", importacion.plantilla_csv(fuente))
        assert list(df.columns) == importacion.COLUMNAS[fuente]
