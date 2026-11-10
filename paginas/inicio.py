import streamlit as st

from core import db, seed
from core.ui import iniciar, rubrica_activa

iniciar("EduVisual")
rubrica = rubrica_activa()

st.markdown(
    "EduVisual **procesa** las evidencias de un **Atributo de Egreso (AE)** para llenar sus formatos: no califica. "
    "Toma las **actividades que el docente ya calificó** (de Google Classroom o capturadas a mano), las "
    "**calificaciones** finales, los resultados **CENEVAL** y las **encuestas** a empleadores y egresados; convierte "
    "todo a la misma escala de 4 niveles y calcula el índice de adopción del atributo."
)
st.markdown(
    "**Cómo se usa**\n"
    "1. **Carga de datos** · importa calificaciones finales, resultados CENEVAL y encuestas (CSV o Excel).\n"
    "2. **Actividades calificadas** · trae de Google Classroom (o captura a mano) las tareas ya calificadas que evalúan el atributo.\n"
    "3. **Panel** · consulta el índice de adopción del AE y el resultado de cada fuente.\n"
    "4. **Reportes** · descarga el reporte en Excel o PDF y la cédula oficial del atributo por unidad de aprendizaje.\n\n"
    "*Opcional:* en **Apoyo del motor** se puede subir un documento sin calificación para que el motor sugiera un nivel que el docente confirma."
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
                detalle = " — UA: " + ", ".join(cfg["asignaturas"])
            elif clave == "ceneval":
                detalle = f" — {cfg['examen']}; áreas: " + ", ".join(cfg["areas"])
            elif clave == "encuestas":
                detalle = (f" — {cfg['pregunta']}" if cfg.get("pregunta") else "") + " (" + " y ".join(cfg.get("tipos", ["empleador", "egresado"])) + ")"
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
    "(SELECT COUNT(*) FROM calificaciones) AS calificaciones, (SELECT COUNT(*) FROM resultados_ceneval) AS ceneval, "
    "(SELECT COUNT(*) FROM encuestas) AS encuestas"
)[0]
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Alumnos", resumen["alumnos"])
c2.metric("Evidencias", resumen["evidencias"], help="Actividades calificadas y documentos evaluados.")
c3.metric("Niveles del docente", resumen["revisadas"], help="Niveles por indicador asignados o confirmados por el docente.")
c4.metric("Calificaciones", resumen["calificaciones"])
c5.metric("Resultados CENEVAL", resumen["ceneval"])
c6.metric("Encuestas", resumen["encuestas"])

st.write("Los datos de ejemplo son sintéticos. Cargarlos **reemplaza** todo lo guardado en la base local.")
if st.button("Cargar datos de ejemplo"):
    st.success(f"Listo: {seed.sembrar()}")
    st.rerun()
