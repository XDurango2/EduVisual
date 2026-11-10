"""Conector de Google Classroom por conexión directa (API de Classroom, sólo lectura).

Requisitos (opcionales; sin ellos la app sigue funcionando con el archivo de calificaciones):
  pip install google-api-python-client google-auth-oauthlib
  y el archivo de credenciales OAuth de tipo «App de escritorio» en data/credenciales/ (el client_secret_*.json que
  descarga Google Cloud Console, con cualquier nombre; con la API de Google Classroom habilitada).

Las funciones reciben el `servicio` ya construido, así que se pueden probar con un servicio simulado.
"""
import json
import sys
from pathlib import Path

from core.conectores import Lectura

ORIGEN = "classroom"
CREDENCIALES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "credenciales"
CLIENTE = CREDENCIALES_DIR / "classroom_client.json"
TOKEN = CREDENCIALES_DIR / "classroom_token.json"
# Permisos de sólo lectura: cursos, tareas con sus calificaciones, lista de alumnos y sus correos.
PERMISOS = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.profile.emails",
]


def archivo_cliente() -> Path | None:
    """El archivo de credenciales OAuth: classroom_client.json o el client_secret_*.json tal como lo descarga Google."""
    if CLIENTE.exists():
        return CLIENTE
    candidatos = sorted(CREDENCIALES_DIR.glob("client_secret*.json")) if CREDENCIALES_DIR.exists() else []
    return candidatos[0] if candidatos else None


def disponible() -> tuple[bool, str]:
    """(listo, motivo): indica si se puede intentar la conexión directa."""
    try:
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
    except ImportError:
        return False, ("Faltan las librerías de Google en el Python que está corriendo la app "
                       f"(`{sys.executable}`). Instálalas con ese mismo Python: "
                       "`python -m pip install google-api-python-client google-auth-oauthlib`.")
    cliente = archivo_cliente()
    if not cliente:
        return False, "Falta el archivo de credenciales OAuth (client_secret_*.json) en `data/credenciales/`."
    try:
        tipo = next(iter(json.loads(cliente.read_text(encoding="utf-8"))))
    except (ValueError, StopIteration):
        return False, f"`{cliente.name}` no es un archivo de credenciales válido."
    if tipo != "installed":
        return False, (f"`{cliente.name}` es una credencial de tipo «{tipo}» (aplicación web). Crea una credencial OAuth de "
                       "tipo **App de escritorio** en Google Cloud Console y descarga su JSON en `data/credenciales/`.")
    return True, ""


# Google puede devolver un permiso con su nombre anterior: son el mismo permiso.
EQUIVALENTES = {
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly":
        "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
}
NOMBRES_PERMISOS = {
    "classroom.courses.readonly": "ver tus clases",
    "classroom.coursework.students.readonly": "ver las tareas y calificaciones",
    "classroom.rosters.readonly": "ver la lista de alumnos",
    "classroom.profile.emails": "ver los correos de los alumnos",
}


def permisos_faltantes(concedidos) -> list[str]:
    """Permisos necesarios que el usuario no concedió (Google deja desmarcar casillas al iniciar sesión)."""
    concedidos = set(concedidos or [])
    return [p for p in PERMISOS if p not in concedidos and EQUIVALENTES.get(p) not in concedidos]


def conectar():
    """Abre el navegador para que el docente inicie sesión con Google y devuelve el servicio de Classroom."""
    import os

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    # Sin esto, oauthlib falla si Google devuelve un permiso con otro nombre o el usuario desmarca alguno;
    # los permisos concedidos se revisan abajo con un mensaje claro.
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    credenciales = Credentials.from_authorized_user_file(str(TOKEN)) if TOKEN.exists() else None
    if credenciales and permisos_faltantes(credenciales.scopes):
        credenciales = None  # token viejo con permisos incompletos: pedir permiso de nuevo
    if not credenciales or not credenciales.valid:
        if credenciales and credenciales.expired and credenciales.refresh_token:
            credenciales.refresh(Request())
        else:
            flujo = InstalledAppFlow.from_client_secrets_file(str(archivo_cliente()), PERMISOS)
            credenciales = flujo.run_local_server(port=0)
            concedidos = (flujo.oauth2session.token or {}).get("scope") or credenciales.scopes
            if isinstance(concedidos, str):
                concedidos = concedidos.split()
            faltan = permisos_faltantes(concedidos)
            if faltan:
                nombres = ", ".join(NOMBRES_PERMISOS.get(p.rsplit("/", 1)[-1], p) for p in faltan)
                raise PermissionError(
                    f"No se concedieron todos los permisos (falta: {nombres}). Vuelve a conectar y marca todas las casillas."
                )
            credenciales = Credentials(**{**_datos(credenciales), "scopes": list(concedidos)})
        TOKEN.write_text(credenciales.to_json(), encoding="utf-8")
    return build("classroom", "v1", credentials=credenciales, cache_discovery=False)


def _datos(c) -> dict:
    return {"token": c.token, "refresh_token": c.refresh_token, "token_uri": c.token_uri,
            "client_id": c.client_id, "client_secret": c.client_secret}


def _paginas(recurso, clave: str, **parametros) -> list[dict]:
    elementos, token = [], None
    while True:
        respuesta = recurso.list(pageToken=token, **parametros).execute()
        elementos += respuesta.get(clave, [])
        token = respuesta.get("nextPageToken")
        if not token:
            return elementos


def cursos(servicio) -> list[dict]:
    """Cursos activos donde el usuario es docente: [{"id", "nombre"}]."""
    lista = _paginas(servicio.courses(), "courses", teacherId="me", courseStates=["ACTIVE"])
    return [{"id": c["id"], "nombre": c.get("name", c["id"])} for c in lista]


def leer(servicio, curso_id: str) -> Lectura:
    """Tareas del curso con las calificaciones ya asignadas por el docente."""
    alumnos = {}
    for a in _paginas(servicio.courses().students(), "students", courseId=curso_id):
        perfil = a.get("profile", {})
        alumnos[a["userId"]] = {
            "nombre": perfil.get("name", {}).get("fullName", ""),
            "correo": perfil.get("emailAddress", "").lower(),
        }

    lectura = Lectura(origen=ORIGEN)
    tareas = _paginas(servicio.courses().courseWork(), "courseWork", courseId=curso_id)
    for tarea in tareas:
        puntos = tarea.get("maxPoints")
        if not puntos:  # tareas sin calificación (material, preguntas sin puntos)
            continue
        fecha = tarea.get("dueDate", {})
        lectura.actividades.append({
            "nombre": tarea["title"], "puntos": float(puntos),
            "fecha": "-".join(str(fecha[k]) for k in ("year", "month", "day") if k in fecha),
        })
        entregas = _paginas(servicio.courses().courseWork().studentSubmissions(), "studentSubmissions",
                            courseId=curso_id, courseWorkId=tarea["id"])
        for n, entrega in enumerate(entregas, start=1):
            alumno = alumnos.get(entrega.get("userId"), {"nombre": "", "correo": ""})
            calificacion = entrega.get("assignedGrade")  # None mientras el docente no la devuelve calificada
            lectura.entregas.append({
                "fila": n, "nombre": alumno["nombre"], "correo": alumno["correo"], "matricula": "",
                "actividad": tarea["title"], "valor": "" if calificacion is None else str(calificacion),
                "puntos": float(puntos),
            })
    return lectura
