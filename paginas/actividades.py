"""Actividades calificadas: trae tareas que el docente ya calificó (Google Classroom o captura manual)
y convierte la calificación al nivel del Atributo de Egreso. Aquí no se califica nada."""
import pandas as pd
import streamlit as st

from core import actividades, db
from core.conectores import classroom_api, classroom_csv
from core.extraccion import texto_de_archivo
from core.ui import iniciar, rubrica_activa

iniciar("Actividades calificadas")
rubrica = rubrica_activa()
minimo = rubrica["nivel_minimo"]
indicadores = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}

st.markdown(
    f"Registra las **actividades ya calificadas** que evalúan **{rubrica['id']} · {rubrica['nombre']}**: la tarea se "
    "califica en la unidad de aprendizaje (en Google Classroom o en papel) y aquí sólo se **procesa**. "
    "La calificación se convierte al nivel del atributo y alimenta el Panel, los reportes y la cédula oficial."
)
tramos = actividades.escala(rubrica)
st.caption(
    "Conversión de calificación a nivel: "
    + " · ".join(f"desde {t['desde']:g} → {t['nivel']} {rubrica['niveles'][str(t['nivel'])]}" for t in tramos)
    + f". Cumple con nivel ≥ {minimo}. Usa únicamente datos sintéticos o anonimizados fuera del ambiente institucional."
)

uas = sorted(
    set(rubrica.get("fuentes", {}).get("calificaciones", {}).get("asignaturas", []))
    | {s["nombre"] for s in db.consulta("SELECT nombre FROM asignaturas WHERE ae_id = ?", (rubrica["id"],))}
)
if not uas:
    st.error("La rúbrica no tiene unidades de aprendizaje vinculadas (fuentes.calificaciones.asignaturas).")
    st.stop()
ua = st.selectbox("Unidad de aprendizaje de la actividad", uas)

mensaje = st.session_state.pop("mensaje_actividades", None)
if mensaje:
    st.success(mensaje)


def elegir_indicadores(clave: str) -> list[str]:
    return st.multiselect(
        "Indicadores que evalúa", list(indicadores), default=list(indicadores), key=clave,
        format_func=lambda i: f"{i} · {indicadores[i]}",
    )


def importar_lectura(lectura, archivo: str, clave: str) -> bool:
    """Elegir actividades de una lectura, validar e importar. Devuelve True si se importó."""
    if not lectura.actividades:
        st.warning("No se encontraron actividades con calificación.")
        return False
    nombres = [a["nombre"] for a in lectura.actividades]
    puntos = {a["nombre"]: a["puntos"] for a in lectura.actividades}
    elegidas = st.multiselect(
        f"Actividades que evalúan {rubrica['id']}", nombres, key=f"{clave}_actividades",
        format_func=lambda n: f"{n} ({puntos[n]:g} puntos)",
        help="Sólo se guardan las actividades que elijas; el resto del archivo no se almacena.",
    )
    if not elegidas:
        st.info("Elige las actividades que son evidencia de este atributo de egreso.")
        return False
    seleccion = {}
    for n in elegidas:
        with st.container(border=True):
            st.markdown(f"**{n}**")
            seleccion[n] = elegir_indicadores(f"{clave}_ind_{n}")

    v = actividades.validar(lectura, seleccion, archivo)
    if v.error_archivo:
        st.error(v.error_archivo)
        return False
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entregas", v.filas)
    c2.metric("Válidas", len(v.validas))
    c3.metric("Rechazadas", len(v.rechazos), f"{v.tasa_rechazo:.1%}", delta_color="inverse")
    c4.metric("Sin calificar", len(v.omitidas), help="Entregas que el docente aún no califica: no se almacenan.")
    if v.rechazos:
        st.markdown("**Entregas rechazadas**")
        st.dataframe(pd.DataFrame(v.rechazos), hide_index=True, width="stretch")
    if not v.validas:
        return False

    vista = pd.DataFrame(v.validas)
    vista["Nivel"] = vista["calificacion"].map(lambda c: actividades.nivel(c, rubrica))
    nuevos = int(vista.drop_duplicates("matricula")["alumno_nuevo"].sum())
    if nuevos:
        st.info(f"{nuevos} alumnos no están registrados: se darán de alta con la primera parte de su correo como matrícula.")
    with st.expander(f"Vista previa ({len(v.validas)} entregas)"):
        st.dataframe(
            vista[["matricula", "nombre", "actividad", "calificacion", "Nivel"]].rename(columns={
                "matricula": "Matrícula", "nombre": "Alumno", "actividad": "Actividad", "calificacion": "Calificación (0-100)"}),
            hide_index=True, width="stretch",
        )
    if st.button(f"Importar {len(v.validas)} entregas calificadas", type="primary", key=f"{clave}_importar"):
        n = actividades.importar(v, rubrica, ua, lectura.origen)
        st.session_state["mensaje_actividades"] = (
            f"Se importaron {n} entregas de {len(elegidas)} actividad(es) en {ua}. Las que ya existían se actualizaron."
        )
        return True
    return False


tab_archivo, tab_directa, tab_manual = st.tabs(
    ["Google Classroom · archivo de calificaciones", "Google Classroom · conexión directa", "Captura manual"]
)

# ------------------------------------------------------------------ Classroom por archivo
with tab_archivo:
    st.markdown(
        "En Classroom abre una tarea de la clase → **Trabajo de los alumnos** → ⚙ (arriba a la derecha) → "
        "**Descargar todas las calificaciones como CSV** y sube aquí ese archivo. No requiere permisos ni contraseñas."
    )
    version = st.session_state.get("version_classroom", 0)
    archivo = st.file_uploader("Archivo de calificaciones de Classroom (CSV o Excel)", type=["csv", "xlsx"],
                               key=f"classroom_{version}")
    if archivo:
        try:
            lectura = classroom_csv.leer(archivo.name, archivo.getvalue())
        except ValueError as e:
            st.error(str(e))
        else:
            if importar_lectura(lectura, archivo.name, f"csv_{version}"):
                st.session_state["version_classroom"] = version + 1
                st.rerun()

# ------------------------------------------------------------------ Classroom por API
with tab_directa:
    listo, motivo = classroom_api.disponible()
    if not listo:
        st.info(
            "La conexión directa deja elegir el curso y sus tareas sin descargar archivos. Está preparada pero "
            f"falta configurarla en esta computadora. {motivo}"
        )
        st.markdown(
            "1. En Google Cloud Console crea un proyecto y habilita la **API de Google Classroom**.\n"
            "2. Crea credenciales **OAuth de tipo App de escritorio** y guarda el JSON descargado "
            "(client_secret_….json) en `data/credenciales/`.\n"
            "3. Instala las librerías: `pip install google-api-python-client google-auth-oauthlib`.\n\n"
            "Mientras tanto, la pestaña de archivo de calificaciones hace lo mismo."
        )
    else:
        if st.button("Conectar con Google Classroom"):
            try:
                st.session_state["classroom_cursos"] = classroom_api.cursos(classroom_api.conectar())
            except Exception as e:  # errores de red o de permisos de Google
                st.error(f"No se pudo conectar con Classroom: {e}")
        lista = st.session_state.get("classroom_cursos")
        if lista is not None and not lista:
            st.warning("Tu cuenta no tiene cursos activos como docente.")
        elif lista:
            curso = st.selectbox("Curso", lista, format_func=lambda c: c["nombre"])
            if st.session_state.get("classroom_curso_leido") != curso["id"]:
                try:
                    with st.spinner("Leyendo tareas y calificaciones…"):
                        st.session_state["classroom_lectura"] = classroom_api.leer(classroom_api.conectar(), curso["id"])
                        st.session_state["classroom_curso_leido"] = curso["id"]
                except Exception as e:
                    st.error(f"No se pudieron leer las tareas: {e}")
            if st.session_state.get("classroom_curso_leido") == curso["id"]:
                if importar_lectura(st.session_state["classroom_lectura"], f"Classroom: {curso['nombre']}", f"api_{curso['id']}"):
                    st.rerun()

# ------------------------------------------------------------------ captura manual
with tab_manual:
    st.markdown("Para actividades calificadas fuera de Classroom: registra la calificación y, si quieres, adjunta el trabajo.")
    alumnos = db.consulta("SELECT id, matricula, nombre FROM alumnos ORDER BY nombre")
    existentes = sorted({a["Actividad"] for a in actividades.registradas(rubrica).to_dict("records")})
    version = st.session_state.get("version_manual", 0)
    with st.form(f"manual_{version}"):
        c1, c2 = st.columns(2)
        actividad = c1.text_input("Nombre de la actividad", placeholder="Ej. Proyecto final: diseño de la solución",
                                  help="Usa el mismo nombre para todos los alumnos de la actividad. Registradas: "
                                       + (", ".join(existentes) if existentes else "ninguna todavía."))
        calificacion = c2.number_input("Calificación (0 a 100)", min_value=0.0, max_value=100.0, value=None, step=1.0)
        NUEVO = "➕ Alumno nuevo"
        opciones = [NUEVO] + [a["matricula"] for a in alumnos]
        nombres_alumnos = {a["matricula"]: a["nombre"] for a in alumnos}
        elegido = st.selectbox("Alumno", opciones, index=1 if alumnos else 0,
                               format_func=lambda m: m if m == NUEVO else f"{m} · {nombres_alumnos[m]}")
        c3, c4 = st.columns(2)
        matricula_nueva = c3.text_input("Matrícula (sólo alumno nuevo)")
        nombre_nuevo = c4.text_input("Nombre (sólo alumno nuevo)")
        elegidos = elegir_indicadores(f"manual_ind_{version}")
        trabajo = st.file_uploader("Trabajo del alumno (opcional: TXT, MD, PDF o DOCX)", type=["txt", "md", "pdf", "docx"])
        enviado = st.form_submit_button("Registrar actividad calificada", type="primary")

    if enviado:
        matricula = matricula_nueva.strip() if elegido == NUEVO else elegido
        nombre = nombre_nuevo.strip() if elegido == NUEVO else nombres_alumnos[elegido]
        error = None
        if not actividad.strip():
            error = "Escribe el nombre de la actividad."
        elif calificacion is None:
            error = "Escribe la calificación."
        elif not matricula or not nombre:
            error = "Para un alumno nuevo escribe su matrícula y su nombre."
        elif not elegidos:
            error = "Elige al menos un indicador."
        texto = ""
        if not error and trabajo:
            try:
                texto = texto_de_archivo(trabajo.name, trabajo.getvalue())
            except ValueError as e:
                error = str(e)
        if error:
            st.error(error)
        else:
            v = actividades.registrar_manual(rubrica, ua, actividad.strip(), matricula, nombre, calificacion, elegidos,
                                             trabajo.name if trabajo else "", texto)
            if v.rechazos or v.error_archivo:
                st.error(v.error_archivo or v.rechazos[0]["motivo"])
            else:
                n = actividades.nivel(calificacion, rubrica)
                st.session_state["mensaje_actividades"] = (
                    f"Registrado: {nombre} · «{actividad.strip()}» · {calificacion:g}/100 → nivel {n} {rubrica['niveles'][str(n)]}."
                )
                st.session_state["version_manual"] = version + 1
                st.rerun()

# ------------------------------------------------------------------ actividades registradas
st.divider()
st.subheader("Actividades registradas")
tabla = actividades.registradas(rubrica)
if tabla.empty:
    st.info("Aún no hay actividades calificadas para este atributo de egreso.")
else:
    st.dataframe(tabla, hide_index=True, width="stretch")
    with st.expander("Eliminar una actividad"):
        filas = tabla.to_dict("records")
        fila = st.selectbox("Actividad", filas, format_func=lambda f: f"{f['Actividad']} · {f['Unidad de aprendizaje']}")
        if st.button("Eliminar todas sus entregas"):
            n = actividades.eliminar(rubrica, fila["Unidad de aprendizaje"], fila["Actividad"])
            st.session_state["mensaje_actividades"] = f"Se eliminaron {n} entregas de «{fila['Actividad']}»."
            st.rerun()
