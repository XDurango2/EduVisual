import json

import streamlit as st

from core import db
from core.ui import iniciar, rubrica_activa

iniciar("Revisión docente")
rubrica = rubrica_activa()
niveles = rubrica["niveles"]
nombres = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}

evidencias = db.consulta(
    """
    SELECT e.id, a.nombre AS alumno, s.nombre AS asignatura, e.nombre_archivo, e.texto,
           SUM(ev.revisado) AS revisadas, COUNT(ev.id) AS total
    FROM evidencias e
    JOIN alumnos a ON a.id = e.alumno_id
    JOIN asignaturas s ON s.id = e.asignatura_id
    LEFT JOIN evaluaciones ev ON ev.evidencia_id = e.id
    GROUP BY e.id ORDER BY (SUM(ev.revisado) = COUNT(ev.id)), e.id
    """
)
if not evidencias:
    st.info("No hay evidencias. Carga los datos de ejemplo o captura una evidencia.")
    st.stop()

pendientes_solo = st.checkbox("Mostrar solo evidencias pendientes de revisión")
if pendientes_solo:
    evidencias = [e for e in evidencias if e["revisadas"] < e["total"]]
    if not evidencias:
        st.success("No hay evidencias pendientes.")
        st.stop()

evidencia = st.selectbox(
    "Evidencia",
    evidencias,
    format_func=lambda e: f"{'✅' if e['revisadas'] == e['total'] else '⏳'} {e['alumno']} · {e['asignatura']} ({e['nombre_archivo']})",
)

with st.expander("Ver evidencia completa"):
    st.text(evidencia["texto"])

filas = db.consulta("SELECT * FROM evaluaciones WHERE evidencia_id = ? ORDER BY indicador_id", (evidencia["id"],))
with st.form(f"revision_{evidencia['id']}"):
    elegidos = {}
    for fila in filas:
        st.markdown(f"#### {fila['indicador_id']} · {nombres.get(fila['indicador_id'], '')}")
        st.caption(f"Motor: {fila['motor']}")
        st.write(f"**Sugerido:** {fila['nivel_sugerido']} · {niveles[str(fila['nivel_sugerido'])]}")
        st.write(fila["justificacion"])
        for cita in json.loads(fila["citas"]):
            st.markdown(f"> {cita}")
        actual = fila["nivel_final"] or fila["nivel_sugerido"]
        elegidos[fila["id"]] = st.select_slider(
            "Nivel final",
            options=[1, 2, 3, 4],
            value=actual,
            format_func=lambda n: f"{n} · {niveles[str(n)]}",
            key=f"nivel_{fila['id']}",
        )
        st.divider()
    if st.form_submit_button("Confirmar revisión", type="primary"):
        for evaluacion_id, nivel in elegidos.items():
            db.guardar_revision(evaluacion_id, nivel)
        st.success("Revisión guardada.")
        st.rerun()
