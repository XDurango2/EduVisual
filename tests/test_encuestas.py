import copy

import pandas as pd

from core import db, importacion
from core.adopcion import resumen_adopcion
from core.importacion import validar_encuestas
from core.rubricas import validar_rubrica


def tabla_enc(filas):
    return pd.DataFrame(filas, columns=importacion.COLUMNAS["encuestas"]).astype(str)


def validar(rubricas, filas):
    return validar_encuestas(tabla_enc(filas), rubricas, "enc.csv")


def test_fila_valida_y_tasa_de_rechazo_cero(rubricas):
    v = validar(rubricas, [["Empresa A", "AE-03", "2026-1", "4", "SI"]])
    assert v.validas == [{"empleador": "Empresa A", "ae_id": "AE-03", "periodo": "2026-1", "respuesta": 4.0}]
    assert v.tasa_rechazo == 0 and v.cumple_meta


def test_acepta_decimal_con_coma_ae_sin_distinguir_mayusculas_y_consentimiento_con_acento(rubricas):
    v = validar(rubricas, [["Empresa A", "ae-03", "2026-1", "4,5", "Sí"]])
    assert v.validas[0]["respuesta"] == 4.5 and v.validas[0]["ae_id"] == "AE-03"


def test_faltan_columnas_obligatorias(rubricas):
    df = pd.DataFrame([["A", "AE-03"]], columns=["empleador", "ae"])
    assert "Faltan columnas obligatorias" in validar_encuestas(df, rubricas).error_archivo


def test_rechaza_filas_invalidas_con_motivo(rubricas):
    v = validar(rubricas, [
        ["", "AE-03", "2026-1", "4", "SI"],            # falta empleador
        ["B", "", "2026-1", "4", "SI"],                # falta AE
        ["C", "AE-03", "2026/1", "4", "SI"],           # periodo inválido
        ["D", "AE-03", "2026-1", "6", "SI"],           # fuera de escala
        ["E", "AE-03", "2026-1", "0", "SI"],           # fuera de escala
        ["F", "AE-03", "2026-1", "alto", "SI"],        # no numérica
        ["G", "AE-03", "2026-1", "4", "tal vez"],      # consentimiento no reconocido
        ["H", "AE-03", "2026-1", "4", ""],             # consentimiento vacío
    ])
    assert v.validas == [] and len(v.rechazos) == 8
    motivos = " | ".join(r["motivo"] for r in v.rechazos)
    for esperado in ("falta el empleador", "falta el AE", "periodo", "fuera de la escala", "no es numérica", "consentimiento"):
        assert esperado in motivos


def test_sin_consentimiento_se_omite_y_no_se_rechaza(rubricas):
    v = validar(rubricas, [["Empresa A", "AE-03", "2026-1", "4", "NO"]])
    assert v.validas == [] and v.rechazos == [] and len(v.omitidas) == 1
    assert "consentimiento" in v.omitidas[0]["motivo"]


def test_se_omiten_ae_desconocido_o_sin_escala_de_encuestas(rubricas):
    sin_encuestas = copy.deepcopy(rubricas["AE-03"])
    sin_encuestas["id"] = "AE-09"
    sin_encuestas["fuentes"].pop("encuestas")
    sin_encuestas["fuentes"]["evidencias"]["peso"] += 0.2
    rub = {**rubricas, "AE-09": sin_encuestas}
    v = validar(rub, [["A", "AE-77", "2026-1", "4", "SI"], ["B", "AE-09", "2026-1", "4", "SI"]])
    assert v.validas == [] and v.rechazos == [] and len(v.omitidas) == 2
    assert "no existe" in v.omitidas[0]["motivo"] and "no tiene escala" in v.omitidas[1]["motivo"]


def test_duplicado_en_el_archivo_se_rechaza(rubricas):
    v = validar(rubricas, [["Empresa A", "AE-03", "2026-1", "4", "SI"], ["empresa a", "AE-03", "2026-1", "3", "SI"]])
    assert len(v.validas) == 1 and "duplicado" in v.rechazos[0]["motivo"]


def test_importar_guarda_actualiza_y_registra_bitacora(rubricas):
    importacion.importar(validar(rubricas, [["Empresa A", "AE-03", "2026-1", "3", "SI"],
                                           ["Empresa B", "AE-03", "2026-1", "5", "NO"]]))
    importacion.importar(validar(rubricas, [["Empresa A", "AE-03", "2026-1", "5", "SI"]]))  # re-importar actualiza
    filas = db.consulta("SELECT empleador, respuesta FROM encuestas_empleadores")
    assert filas == [{"empleador": "Empresa A", "respuesta": 5.0}]  # Empresa B no dio consentimiento
    bitacora = db.consulta("SELECT filas, aceptadas, omitidas FROM cargas WHERE fuente = 'encuestas' ORDER BY id")
    assert bitacora == [{"filas": 2, "aceptadas": 1, "omitidas": 1}, {"filas": 1, "aceptadas": 1, "omitidas": 0}]
    assert db.consulta("SELECT COUNT(*) AS n FROM alumnos")[0]["n"] == 0  # no crea alumnos


def test_adopcion_convierte_respuestas_a_niveles(rubricas):
    r = rubricas["AE-03"]
    # Escala: <2.5 -> 1, <3.5 -> 2, <4.5 -> 3, >=4.5 -> 4; nivel mínimo del AE = 3.
    importacion.importar(validar(rubricas, [
        ["A", "AE-03", "2026-1", "1", "SI"], ["B", "AE-03", "2026-1", "3", "SI"],
        ["C", "AE-03", "2026-1", "4", "SI"], ["D", "AE-03", "2026-1", "5", "SI"],
    ]))
    tabla, indice = resumen_adopcion(r)
    fila = tabla.set_index("fuente").loc["encuestas"]
    assert fila["Registros"] == 4 and fila["Sujetos"] == 4 and fila["Unidad"] == "empleadores"
    assert fila["Nivel promedio"] == (1 + 2 + 3 + 4) / 4
    assert fila["Cumplimiento"] == 0.5 and indice == 0.5  # sólo esta fuente tiene datos


def test_validador_de_rubrica_revisa_escala_de_encuestas(rubricas):
    r = copy.deepcopy(rubricas["AE-03"])
    r["fuentes"]["encuestas"]["escala"] = [{"desde": 0, "nivel": 1}, {"desde": 3, "nivel": 7}]
    errores = " | ".join(validar_rubrica(r))
    assert "escala de encuestas debe iniciar en 1" in errores and "solo admite niveles 1 a 4" in errores


def test_plantilla_csv_valida_con_la_propia_validacion(rubricas):
    from io import BytesIO
    df = pd.read_csv(BytesIO(importacion.plantilla_csv("encuestas")), dtype=str)
    assert list(df.columns) == importacion.COLUMNAS["encuestas"]
    assert len(validar_encuestas(df, rubricas).validas) == 1
