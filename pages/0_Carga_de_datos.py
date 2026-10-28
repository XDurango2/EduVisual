import pandas as pd
import streamlit as st

from core import db, importacion
from core.rubricas import cargar_rubricas
from core.ui import iniciar

iniciar("Carga de datos")
st.markdown(
    "Integra las fuentes externas del Atributo de Egreso: **calificaciones** (RF-001), **resultados CENEVAL** "
    "(RF-002) y **encuestas a empleadores** (RF-003). Cada archivo se valida fila por fila antes de guardarse. "
    f"La meta del Plan de Calidad es que cada carga tenga **menos de {importacion.META_RECHAZO:.0%} de registros rechazados**."
)
st.caption(
    "Minimización de datos: sólo se guardan asignaturas y áreas CENEVAL vinculadas a un Atributo de Egreso en su rúbrica; "
    "las demás filas se omiten sin almacenarse. De las encuestas sólo se guardan las respuestas de empleadores que dieron su "
    "consentimiento. Usa únicamente datos sintéticos o anonimizados fuera del ambiente institucional."
)

rubricas = cargar_rubricas()
VALIDADORES = {
    "calificaciones": importacion.validar_calificaciones,
    "ceneval": importacion.validar_ceneval,
    "encuestas": importacion.validar_encuestas,
}
DESCRIPCION = {
    "calificaciones": (
        "Columnas: `matricula`, `nombre` (sólo para alumnos nuevos), `asignatura`, `periodo` (AAAA-N, ej. 2026-1) "
        "y `calificacion` (0 a 100)."
    ),
    "ceneval": (
        "Columnas: `matricula`, `nombre` (sólo para alumnos nuevos), `examen`, `area`, `periodo` (AAAA-N), "
        "`desempeno` (ANS, DS o DSS) y `puntaje` (opcional, 700 a 1300). "
        "Formato preliminar: confirmar con los encargados de CENEVAL."
    ),
    "encuestas": (
        "Columnas: `empleador`, `ae` (id del Atributo de Egreso, ej. AE-03), `periodo` (AAAA-N), "
        "`respuesta` (valoración de 1 a 5 de la capacidad de los egresados) y `consentimiento` (SI o NO). "
        "Las filas sin consentimiento se omiten sin almacenarse. Una fila por empleador, AE y periodo."
    ),
}


def seccion(fuente: str):
    st.markdown(DESCRIPCION[fuente])
    st.download_button(
        "Descargar plantilla CSV", importacion.plantilla_csv(fuente), f"plantilla_{fuente}.csv", "text/csv",
        key=f"plantilla_{fuente}",
    )
    mensaje = st.session_state.pop(f"mensaje_{fuente}", None)
    if mensaje:
        st.success(mensaje)
    # La clave cambia después de cada importación para vaciar el selector y evitar importar dos veces.
    version = st.session_state.get(f"version_{fuente}", 0)
    archivo = st.file_uploader("Archivo CSV o Excel", type=["csv", "xlsx"], key=f"archivo_{fuente}_{version}")
    if not archivo:
        return

    try:
        df = importacion.leer_tabla(archivo.name, archivo.getvalue())
    except ValueError as e:
        st.error(str(e))
        return
    v = VALIDADORES[fuente](df, rubricas, archivo.name)
    if v.error_archivo:
        st.error(v.error_archivo)
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Filas", v.filas)
    c2.metric("Válidas", len(v.validas))
    c3.metric("Rechazadas", len(v.rechazos), f"{v.tasa_rechazo:.1%}", delta_color="inverse")
    c4.metric("Omitidas", len(v.omitidas), help="Filas válidas que no se almacenan: no tributan a ningún AE o (encuestas) sin consentimiento del empleador.")

    if v.cumple_meta:
        st.success(f"La carga cumple la meta de calidad: {v.tasa_rechazo:.1%} de rechazos (meta < {importacion.META_RECHAZO:.0%}).")
    else:
        st.warning(
            f"La carga no cumple la meta de calidad: {v.tasa_rechazo:.1%} de rechazos (meta < {importacion.META_RECHAZO:.0%}). "
            "Corrige el archivo de origen o importa sólo las filas válidas; la carga quedará registrada en la bitácora."
        )

    if v.rechazos:
        st.markdown("**Filas rechazadas**")
        st.dataframe(pd.DataFrame(v.rechazos), hide_index=True, width="stretch")
    if v.omitidas:
        with st.expander(f"Filas omitidas por minimización ({len(v.omitidas)})"):
            st.dataframe(pd.DataFrame(v.omitidas), hide_index=True, width="stretch")
    if v.validas:
        with st.expander(f"Vista previa de filas válidas ({len(v.validas)})"):
            st.dataframe(pd.DataFrame(v.validas), hide_index=True, width="stretch")

        if st.button(f"Importar {len(v.validas)} filas válidas", type="primary", key=f"importar_{fuente}"):
            n = importacion.importar(v)
            st.session_state[f"mensaje_{fuente}"] = (
                f"Se importaron {n} registros de {archivo.name}. Los registros ya existentes se actualizaron."
            )
            st.session_state[f"version_{fuente}"] = version + 1
            st.rerun()


tab_cal, tab_cen, tab_enc = st.tabs(["Calificaciones (RF-001)", "Resultados CENEVAL (RF-002)", "Encuestas a empleadores (RF-003)"])
with tab_cal:
    seccion("calificaciones")
with tab_cen:
    seccion("ceneval")
with tab_enc:
    seccion("encuestas")

st.divider()
st.subheader("Datos integrados")
totales = db.consulta(
    "SELECT (SELECT COUNT(*) FROM calificaciones) AS calificaciones, "
    "(SELECT COUNT(*) FROM resultados_ceneval) AS ceneval, (SELECT COUNT(*) FROM alumnos) AS alumnos, "
    "(SELECT COUNT(*) FROM encuestas_empleadores) AS encuestas, "
    "(SELECT COUNT(DISTINCT empleador) FROM encuestas_empleadores) AS empleadores"
)[0]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Calificaciones", totales["calificaciones"])
c2.metric("Resultados CENEVAL", totales["ceneval"])
c3.metric("Alumnos", totales["alumnos"])
c4.metric("Encuestas", totales["encuestas"])
c5.metric("Empleadores", totales["empleadores"])

st.subheader("Bitácora de cargas")
bitacora = db.dataframe(
    "SELECT datetime(fecha, 'localtime') AS Fecha, fuente AS Fuente, archivo AS Archivo, filas AS Filas, aceptadas AS Aceptadas, "
    "rechazadas AS Rechazadas, omitidas AS Omitidas FROM cargas ORDER BY id DESC"
)
if bitacora.empty:
    st.info("Aún no hay cargas registradas.")
else:
    bitacora["% rechazo"] = (bitacora["Rechazadas"] / bitacora["Filas"]).map(lambda x: f"{x:.1%}")
    bitacora["Cumple meta"] = (bitacora["Rechazadas"] / bitacora["Filas"] < importacion.META_RECHAZO).map({True: "Sí", False: "No"})
    st.dataframe(bitacora, hide_index=True, width="stretch")
