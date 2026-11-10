"""Apoyo del motor (opcional): para documentos que NO tienen calificación. El motor sugiere un nivel por
indicador y el docente confirma o corrige. La vía principal son las actividades ya calificadas (paginas/actividades.py)."""
import json

import streamlit as st

from core import db
from core.evaluador import evaluar
from core.extraccion import texto_de_archivo
from core.ui import iniciar, rubrica_activa

iniciar("Apoyo del motor (opcional)")
rubrica = rubrica_activa()
niveles = rubrica["niveles"]
nombres = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}
minimo = rubrica["nivel_minimo"]

st.info(
    "Esta página es **opcional**. Las actividades que ya tienen calificación se registran en **Actividades calificadas**. "
    "Úsala sólo para documentos sin calificación (proyecto terminal, reporte de prácticas, portafolio…): el motor "
    "**sugiere** un nivel por indicador y **el docente decide**; nada cuenta como definitivo hasta que lo confirma."
)
st.markdown(
    f"El motor compara el documento con la rúbrica de **{rubrica['id']} · {rubrica['nombre']}** y muestra su sugerencia "
    "con justificación y citas."
)


def nombre_motor(motor: str) -> str:
    if motor.startswith("ollama"):
        return f"modelo de lenguaje local ({motor.split(':', 1)[1]})"
    return "evaluador por palabras clave"


# ------------------------------------------------------------------ egresado
egresados = db.consulta("SELECT id, matricula, nombre FROM alumnos ORDER BY nombre")
if not egresados:
    st.info(
        "Todavía no hay alumnos registrados. Se registran al cargar sus calificaciones o resultados CENEVAL "
        "en **Carga de datos**, al importar una actividad calificada, o con los datos de ejemplo de la página **Inicio**."
    )
    st.stop()

documentos = db.consulta(
    """SELECT e.id, e.alumno_id, e.nombre_archivo, e.tipo_documento, e.texto, s.nombre AS ua,
              datetime(e.fecha, 'localtime') AS fecha,
              COALESCE(SUM(ev.revisado), 0) AS revisadas, COUNT(ev.id) AS total
       FROM evidencias e
       JOIN asignaturas s ON s.id = e.asignatura_id
       LEFT JOIN evaluaciones ev ON ev.evidencia_id = e.id
       WHERE s.ae_id = ? AND e.origen = ?
       GROUP BY e.id ORDER BY e.id""",
    (rubrica["id"], db.ORIGEN_MOTOR),
)
por_egresado: dict[int, list[dict]] = {}
for d in documentos:
    d["pendiente"] = d["revisadas"] < d["total"]
    por_egresado.setdefault(d["alumno_id"], []).append(d)


def estado_egresado(alumno_id: int) -> str:
    docs = por_egresado.get(alumno_id, [])
    if not docs:
        return "Sin documentos evaluados todavía."
    pendientes = sum(d["pendiente"] for d in docs)
    estado = f"{len(docs)} documento{'s' if len(docs) > 1 else ''} evaluado{'s' if len(docs) > 1 else ''}"
    return estado + (f" · {pendientes} por confirmar" if pendientes else " · todos confirmados")


# Las opciones son ids (etiqueta estable): si la etiqueta incluyera los conteos, Streamlit
# conservaría el texto viejo después de evaluar un documento.
por_id = {a["id"]: a for a in egresados}
solo_pendientes = st.checkbox("Mostrar solo quienes tienen sugerencias por confirmar")
opciones = [i for i in por_id if not solo_pendientes or any(d["pendiente"] for d in por_egresado.get(i, []))]
if not opciones:
    st.success("No hay evaluaciones pendientes de confirmar.")
    st.stop()
egresado = por_id[st.selectbox("Alumno o egresado", opciones, key="egresado",
                               format_func=lambda i: f"{por_id[i]['matricula']} · {por_id[i]['nombre']}")]
st.caption(estado_egresado(egresado["id"]))
docs_egresado = por_egresado.get(egresado["id"], [])

# ------------------------------------------------------------------ paso 1: subir documento
uas = sorted(
    set(rubrica.get("fuentes", {}).get("calificaciones", {}).get("asignaturas", []))
    | {s["nombre"] for s in db.consulta("SELECT nombre FROM asignaturas WHERE ae_id = ?", (rubrica["id"],))}
)

with st.expander("Paso 1 · Subir un documento", expanded=not docs_egresado):
    if not uas:
        st.error("La rúbrica no tiene unidades de aprendizaje vinculadas (fuentes.calificaciones.asignaturas).")
        st.stop()
    c1, c2 = st.columns(2)
    tipo = c1.selectbox("Tipo de documento", db.TIPOS_DOCUMENTO)
    ua = c2.selectbox(
        "Unidad de aprendizaje donde se elaboró",
        uas,
        help="Dato secundario: sólo se usa para agrupar resultados en la cédula oficial por unidad de aprendizaje.",
    )
    archivo = st.file_uploader("Documento (TXT, MD, PDF o DOCX)", type=["txt", "md", "pdf", "docx"],
                               key=f"archivo_{st.session_state.get('version_archivo', 0)}")
    texto_manual = st.text_area("…o pega el texto del documento", height=150,
                                key=f"texto_{st.session_state.get('version_archivo', 0)}")

    if st.button("Evaluar documento", type="primary"):
        try:
            if archivo:
                nombre_archivo, texto = archivo.name, texto_de_archivo(archivo.name, archivo.getvalue())
            else:
                nombre_archivo, texto = "texto_pegado.txt", texto_manual
        except ValueError as e:
            st.error(str(e))
            st.stop()
        if not texto.strip():
            st.error("El documento está vacío: sube un archivo o pega su texto.")
            st.stop()

        with st.spinner("Evaluando el documento con la rúbrica…"):
            ua_id = db.obtener_o_crear_asignatura(ua, rubrica["id"])
            evidencia_id = db.guardar_evidencia(egresado["id"], ua_id, nombre_archivo, texto, tipo)
            resultados, aviso = evaluar(texto, rubrica)
            for r in resultados:
                db.guardar_evaluacion(evidencia_id, r)

        st.session_state["documento"] = evidencia_id
        st.session_state["version_archivo"] = st.session_state.get("version_archivo", 0) + 1
        st.session_state["mensaje"] = (
            ("warning", aviso) if aviso else
            ("success", "Documento evaluado. Revisa la sugerencia del motor y confirma cada nivel en el paso 2.")
        )
        st.rerun()

mensaje = st.session_state.pop("mensaje", None)
if mensaje:
    getattr(st, mensaje[0])(mensaje[1])

# ------------------------------------------------------------------ paso 2: revisar y confirmar
st.subheader("Paso 2 · Revisar y confirmar la evaluación")
if not docs_egresado:
    st.info("Este egresado aún no tiene documentos evaluados. Sube uno en el paso 1.")
    st.stop()

ids = [d["id"] for d in docs_egresado]
preferido = st.session_state.get("documento")
indice = ids.index(preferido) if preferido in ids else next((i for i, d in enumerate(docs_egresado) if d["pendiente"]), 0)
doc = st.selectbox(
    "Documento",
    docs_egresado,
    index=indice,
    format_func=lambda d: f"{'⏳ por confirmar' if d['pendiente'] else '✅ confirmado'} · {d['tipo_documento']} · {d['nombre_archivo']} · {d['fecha']}",
)
st.caption(f"Unidad de aprendizaje: {doc['ua']}")
with st.expander("Ver el documento completo"):
    st.text(doc["texto"])

filas = db.consulta("SELECT * FROM evaluaciones WHERE evidencia_id = ? ORDER BY indicador_id", (doc["id"],))
with st.form(f"revision_{doc['id']}"):
    elegidos = {}
    for fila in filas:
        st.markdown(f"#### {fila['indicador_id']} · {nombres.get(fila['indicador_id'], '')}")
        sugerido = fila["nivel_sugerido"]
        st.markdown(
            f"**Sugerencia del motor:** {sugerido} · {niveles[str(sugerido)]}  \n"
            f"<small>Sugerido por el {nombre_motor(fila['motor'])}</small>",
            unsafe_allow_html=True,
        )
        st.write(fila["justificacion"])
        for cita in json.loads(fila["citas"]):
            st.markdown(f"> {cita}")
        elegidos[fila["id"]] = st.select_slider(
            "Nivel confirmado por el docente",
            options=[1, 2, 3, 4],
            value=fila["nivel_final"] or sugerido,
            format_func=lambda n: f"{n} · {niveles[str(n)]}",
            key=f"nivel_{fila['id']}",
        )
        st.divider()
    if st.form_submit_button("Confirmar evaluación", type="primary"):
        for evaluacion_id, nivel in elegidos.items():
            db.guardar_revision(evaluacion_id, nivel)
        cumplen = sum(n >= minimo for n in elegidos.values())
        st.session_state["documento"] = doc["id"]
        st.session_state["mensaje"] = (
            "success",
            f"Evaluación confirmada: {cumplen} de {len(elegidos)} indicadores con nivel ≥ {minimo} ({niveles[str(minimo)]}).",
        )
        st.rerun()
