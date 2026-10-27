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

validacion = rubrica.get("validacion", {"estado": "pendiente"})
if validacion["estado"] == "validada":
    st.success(f"Rúbrica validada por {validacion.get('validado_por')} el {validacion.get('fecha')}.")
else:
    st.warning(f"Validación académica de la rúbrica: **{validacion['estado']}**. {validacion.get('observaciones', '')}")

fuentes = rubrica.get("fuentes", {})
if fuentes:
    with st.expander("Fuentes de datos vinculadas a este Atributo de Egreso"):
        for clave, cfg in fuentes.items():
            detalle = ""
            if clave == "calificaciones":
                detalle = " — asignaturas: " + ", ".join(cfg["asignaturas"])
            elif clave == "ceneval":
                detalle = f" — {cfg['examen']}; áreas: " + ", ".join(cfg["areas"])
            st.markdown(f"- **{clave.capitalize()}** (peso {cfg['peso']:.0%}){detalle}")
for ind in rubrica["indicadores"]:
    with st.expander(f"{ind['id']} · {ind['nombre']}"):
        st.write(ind["descripcion"])
        for nivel, desc in ind["niveles"].items():
            st.markdown(f"- **{nivel} · {rubrica['niveles'][nivel]}:** {desc}")

st.divider()
resumen = db.consulta(
    "SELECT (SELECT COUNT(*) FROM alumnos) AS alumnos, (SELECT COUNT(*) FROM evidencias) AS evidencias, "
    "(SELECT COUNT(*) FROM evaluaciones WHERE revisado = 1) AS revisadas, "
    "(SELECT COUNT(*) FROM calificaciones) AS calificaciones, (SELECT COUNT(*) FROM resultados_ceneval) AS ceneval"
)[0]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Alumnos", resumen["alumnos"])
c2.metric("Evidencias", resumen["evidencias"])
c3.metric("Evaluaciones revisadas", resumen["revisadas"])
c4.metric("Calificaciones", resumen["calificaciones"])
c5.metric("Resultados CENEVAL", resumen["ceneval"])

st.write("Los datos de ejemplo son sintéticos. Cargarlos **reemplaza** todo lo guardado en la base local.")
if st.button("Cargar datos de ejemplo"):
    st.success(f"Listo: {seed.sembrar()}")
    st.rerun()
