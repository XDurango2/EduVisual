import streamlit as st

from core import db, seed
from core.ui import iniciar, rubrica_activa

iniciar("EduVisual")
rubrica = rubrica_activa()

st.markdown(
    "Prueba de concepto para evaluar **Atributos de Egreso** a partir de evidencias estudiantiles. "
    "El motor sugiere un nivel por indicador con justificación y citas; el docente confirma o corrige."
)

st.subheader(f"{rubrica['id']} · {rubrica['nombre']}")
st.caption(f"{rubrica['programa']} · {rubrica['descripcion']}")
for ind in rubrica["indicadores"]:
    with st.expander(f"{ind['id']} · {ind['nombre']}"):
        st.write(ind["descripcion"])
        for nivel, desc in ind["niveles"].items():
            st.markdown(f"- **{nivel} · {rubrica['niveles'][nivel]}:** {desc}")

st.divider()
resumen = db.consulta(
    "SELECT (SELECT COUNT(*) FROM alumnos) AS alumnos, (SELECT COUNT(*) FROM evidencias) AS evidencias, "
    "(SELECT COUNT(*) FROM evaluaciones WHERE revisado = 1) AS revisadas"
)[0]
c1, c2, c3 = st.columns(3)
c1.metric("Alumnos", resumen["alumnos"])
c2.metric("Evidencias", resumen["evidencias"])
c3.metric("Evaluaciones revisadas", resumen["revisadas"])

st.write("Los datos de ejemplo son sintéticos. Cargarlos **reemplaza** todo lo guardado en la base local.")
if st.button("Cargar datos de ejemplo"):
    st.success(f"Listo: {seed.sembrar()}")
    st.rerun()
