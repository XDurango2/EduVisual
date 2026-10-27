import pandas as pd
import streamlit as st

from core import db, importacion
from core.rubricas import cargar_rubricas
from core.ui import iniciar

iniciar("Carga de datos")
st.markdown(
    "Integra las fuentes externas del Atributo de Egreso: **calificaciones** (RF-001) y **resultados CENEVAL** "
    "(RF-002). Cada archivo se valida fila por fila antes de guardarse. "
    f"La meta del Plan de Calidad es que cada carga tenga **menos de {importacion.META_RECHAZO:.0%} de registros rechazados**."
)
st.caption(
    "Minimización de datos: sólo se guardan asignaturas y áreas CENEVAL vinculadas a un Atributo de Egreso en su rúbrica; "
    "las demás filas se omiten sin almacenarse. Usa únicamente datos sintéticos o anonimizados fuera del ambiente institucional."
)

rubricas = cargar_rubricas()
VALIDADORES = {"calificaciones": importacion.validar_calificaciones, "ceneval": importacion.validar_ceneval}
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
    c4.metric("Omitidas", len(v.omitidas), help="Filas válidas cuya asignatura o área no tributa a ningún AE.")

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


tab_cal, tab_cen = st.tabs(["Calificaciones (RF-001)", "Resultados CENEVAL (RF-002)"])
with tab_cal:
    seccion("calificaciones")
with tab_cen:
    seccion("ceneval")

st.divider()
st.subheader("Datos integrados")
totales = db.consulta(
    "SELECT (SELECT COUNT(*) FROM calificaciones) AS calificaciones, "
    "(SELECT COUNT(*) FROM resultados_ceneval) AS ceneval, (SELECT COUNT(*) FROM alumnos) AS alumnos"
)[0]
c1, c2, c3 = st.columns(3)
c1.metric("Calificaciones", totales["calificaciones"])
c2.metric("Resultados CENEVAL", totales["ceneval"])
c3.metric("Alumnos", totales["alumnos"])

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
