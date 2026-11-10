"""Actividades calificadas: conector de Classroom (archivo y API), conversión a niveles y captura manual."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from core import actividades, db, seed
from core.adopcion import resumen_adopcion
from core.conectores import classroom_api, classroom_csv
from core.resumen import metricas

PAGINA = str(Path(__file__).resolve().parent.parent / "paginas" / "actividades.py")
CSV = (
    "Apellidos,Nombre,Dirección de correo electrónico,Proyecto final,Tarea 2,Examen\n"
    "Fecha,,,15 may 2026,1 mar 2026,2 mar 2026\n"
    "Puntos,,,50,10,100\n"
    "Torres,Ana,ana@ejemplo.edu.mx,45,8,70\n"
    "Ramírez,Luis,luis@ejemplo.edu.mx,30,,90\n"
    "Soto,María,maria@ejemplo.edu.mx,abc,10,80\n"
).encode("utf-8")


def test_lee_el_archivo_de_classroom():
    lectura = classroom_csv.leer("calificaciones.csv", CSV)
    assert [(a["nombre"], a["puntos"]) for a in lectura.actividades] == [("Proyecto final", 50), ("Tarea 2", 10), ("Examen", 100)]
    assert len(lectura.entregas) == 9
    primera = lectura.entregas[0]
    assert (primera["nombre"], primera["correo"], primera["valor"], primera["puntos"]) == ("Ana Torres", "ana@ejemplo.edu.mx", "45", 50)


def test_lee_encabezados_en_ingles_y_sin_fila_de_puntos():
    lectura = classroom_csv.leer("grades.csv", b"Last Name,First Name,Email Address,Essay\nDate,,,Sep 1\nDoe,Jane,jane@x.org,88\n")
    assert lectura.actividades == [{"nombre": "Essay", "puntos": 100.0, "fecha": "Sep 1"}]
    assert lectura.entregas[0]["nombre"] == "Jane Doe"


def test_valida_e_importa_solo_las_actividades_elegidas(rubricas):
    rubrica = rubricas["AE-03"]
    lectura = classroom_csv.leer("calificaciones.csv", CSV)
    v = actividades.validar(lectura, {"Proyecto final": ["I1", "I2", "I3"], "Tarea 2": ["I2"]}, "calificaciones.csv")
    assert v.filas == 6  # el examen no se eligió: ni se cuenta ni se guarda
    assert len(v.validas) == 4 and len(v.omitidas) == 1 and len(v.rechazos) == 1
    assert "no es numérica" in v.rechazos[0]["motivo"]

    assert actividades.importar(v, rubrica, "Ingeniería de Software", lectura.origen) == 4
    ana = db.consulta(
        """SELECT e.actividad, e.calificacion, e.origen, ev.indicador_id, ev.nivel_final, ev.revisado, ev.motor
           FROM evidencias e JOIN evaluaciones ev ON ev.evidencia_id = e.id JOIN alumnos a ON a.id = e.alumno_id
           WHERE a.correo = 'ana@ejemplo.edu.mx' ORDER BY e.actividad, ev.indicador_id"""
    )
    # 45/50 = 90 -> nivel 4 en los tres indicadores; 8/10 = 80 -> nivel 3 en I2.
    assert [(f["actividad"], f["indicador_id"], f["nivel_final"]) for f in ana] == [
        ("Proyecto final", "I1", 4), ("Proyecto final", "I2", 4), ("Proyecto final", "I3", 4), ("Tarea 2", "I2", 3)]
    assert all(f["revisado"] == 1 and f["motor"] == db.MOTOR_CALIFICACION and f["origen"] == "classroom" for f in ana)
    assert db.consulta("SELECT matricula FROM alumnos WHERE correo = 'luis@ejemplo.edu.mx'") == [{"matricula": "luis"}]
    assert db.consulta("SELECT fuente, aceptadas, rechazadas, omitidas FROM cargas") == [
        {"fuente": "actividades (classroom)", "aceptadas": 4, "rechazadas": 1, "omitidas": 1}]

    tabla, indice = resumen_adopcion(rubrica)
    assert tabla.set_index("fuente").loc["evidencias", "Registros"] == 8 and indice is not None
    m = metricas(rubrica)
    assert m["calificadas"] == 8 and m["evaluaciones"] == 0 and m["concordancia"] is None


def test_reimportar_actualiza_sin_duplicar(rubricas):
    rubrica = rubricas["AE-03"]
    for contenido in (CSV, CSV.replace(b",45,8,70", b",20,8,70")):
        lectura = classroom_csv.leer("c.csv", contenido)
        actividades.importar(actividades.validar(lectura, {"Proyecto final": ["I1"]}), rubrica, "Ingeniería de Software", "classroom")
    filas = db.consulta("SELECT e.calificacion FROM evidencias e JOIN alumnos a ON a.id = e.alumno_id WHERE a.correo = 'ana@ejemplo.edu.mx'")
    assert filas == [{"calificacion": 40.0}]
    assert db.consulta("SELECT COUNT(*) AS n FROM evaluaciones")[0]["n"] == 2  # Ana y Luis, un indicador cada uno


def test_identifica_alumnos_ya_registrados_por_nombre(rubricas):
    alumno_id = db.obtener_o_crear_alumno("1234567", "Ana Torres")
    lectura = classroom_csv.leer("c.csv", CSV)
    actividades.importar(actividades.validar(lectura, {"Proyecto final": ["I1"]}), rubricas["AE-03"], "Ingeniería de Software", "classroom")
    assert db.consulta("SELECT alumno_id FROM evidencias WHERE alumno_id = ?", (alumno_id,))
    assert db.consulta("SELECT correo FROM alumnos WHERE id = ?", (alumno_id,)) == [{"correo": "ana@ejemplo.edu.mx"}]


def test_captura_manual_y_eliminar(rubricas):
    rubrica = rubricas["AE-03"]
    v = actividades.registrar_manual(rubrica, "Ingeniería de Software", "Exposición", "A0900", "Rosa Lima", 72, ["I3"],
                                     "exposicion.txt", "texto del trabajo")
    assert not v.rechazos and len(v.validas) == 1
    fila = db.consulta("SELECT e.origen, e.texto, e.nombre_archivo, ev.nivel_final FROM evidencias e JOIN evaluaciones ev ON ev.evidencia_id = e.id")
    assert fila == [{"origen": "manual", "texto": "texto del trabajo", "nombre_archivo": "exposicion.txt", "nivel_final": 2}]
    resumen = actividades.registradas(rubrica)
    assert resumen["Actividad"].tolist() == ["Exposición"] and resumen["Origen"].tolist() == ["Captura manual"]
    assert actividades.registrar_manual(rubrica, "Ingeniería de Software", "Exposición", "A0901", "", 80, ["I3"]).rechazos
    assert actividades.eliminar(rubrica, "Ingeniería de Software", "Exposición") == 1
    assert db.consulta("SELECT COUNT(*) AS n FROM evaluaciones")[0]["n"] == 0


def test_las_actividades_no_aparecen_como_documentos_del_motor():
    seed.sembrar()
    assert db.consulta("SELECT COUNT(*) AS n FROM evidencias WHERE origen = 'classroom'")[0]["n"] == 15  # 8 + 7 (una sin calificar)
    at = AppTest.from_file(str(Path(PAGINA).parent / "evaluar_egresado.py"), default_timeout=60).run()
    assert not at.exception
    documentos = next(s for s in at.selectbox if s.label == "Documento")
    assert len(documentos.options) == 1 and "Proyecto terminal" in documentos.options[0]


class _Llamada:
    def __init__(self, respuesta):
        self.respuesta = respuesta

    def execute(self):
        return self.respuesta


class _Recurso:
    """Simula un recurso de la API: `list()` devuelve páginas y los sub-recursos se pasan como atributos."""

    def __init__(self, clave, paginas, **hijos):
        self.clave, self.paginas, self.hijos = clave, paginas, hijos

    def list(self, pageToken=None, **_):
        i = int(pageToken or 0)
        respuesta = {self.clave: self.paginas[i]}
        if i + 1 < len(self.paginas):
            respuesta["nextPageToken"] = str(i + 1)
        return _Llamada(respuesta)

    def __getattr__(self, nombre):
        return lambda: self.__dict__["hijos"][nombre]


def test_conector_api_con_servicio_simulado(rubricas):
    entregas = _Recurso("studentSubmissions", [[{"userId": "u1", "assignedGrade": 18}], [{"userId": "u2"}]])
    tareas = _Recurso("courseWork", [[{"id": "t1", "title": "Prototipo", "maxPoints": 20, "dueDate": {"year": 2026, "month": 5, "day": 2}},
                                      {"id": "t2", "title": "Lectura sin puntos"}]], studentSubmissions=entregas)
    alumnos = _Recurso("students", [[{"userId": "u1", "profile": {"name": {"fullName": "Ana Torres"}, "emailAddress": "Ana@ejemplo.edu.mx"}},
                                     {"userId": "u2", "profile": {"name": {"fullName": "Luis Ramírez"}, "emailAddress": "luis@ejemplo.edu.mx"}}]])
    cursos = _Recurso("courses", [[{"id": "c1", "name": "Ingeniería de Software 2026-1"}]], courseWork=tareas, students=alumnos)

    class Servicio:
        def courses(self):
            return cursos

    assert classroom_api.cursos(Servicio()) == [{"id": "c1", "nombre": "Ingeniería de Software 2026-1"}]
    lectura = classroom_api.leer(Servicio(), "c1")
    assert lectura.actividades == [{"nombre": "Prototipo", "puntos": 20.0, "fecha": "2026-5-2"}]
    v = actividades.validar(lectura, {"Prototipo": ["I1"]}, "Classroom")
    assert [(f["correo"], f["calificacion"]) for f in v.validas] == [("ana@ejemplo.edu.mx", 90.0)]
    assert len(v.omitidas) == 1  # Luis aún no tiene calificación


def test_pagina_importa_un_archivo_de_classroom():
    at = AppTest.from_file(PAGINA, default_timeout=60).run()
    assert not at.exception
    assert any("Aún no hay actividades" in i.value for i in at.info)


def test_pagina_captura_manual():
    seed.sembrar()
    antes = db.consulta("SELECT COUNT(*) AS n FROM evidencias")[0]["n"]
    at = AppTest.from_file(PAGINA, default_timeout=60).run()
    assert not at.exception
    next(t for t in at.text_input if t.label == "Nombre de la actividad").input("Bitácora de diseño")
    next(n for n in at.number_input if n.label.startswith("Calificación")).set_value(95)
    next(b for b in at.button if b.label == "Registrar actividad calificada").click().run()
    assert not at.exception and not at.error
    assert db.consulta("SELECT COUNT(*) AS n FROM evidencias")[0]["n"] == antes + 1
    nueva = db.consulta("SELECT actividad, calificacion, origen FROM evidencias ORDER BY id DESC LIMIT 1")[0]
    assert nueva == {"actividad": "Bitácora de diseño", "calificacion": 95.0, "origen": "manual"}
    assert any("nivel 4" in s.value for s in at.success)


def test_detecta_el_archivo_y_el_tipo_de_credencial(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(classroom_api, "CREDENCIALES_DIR", tmp_path)
    monkeypatch.setattr(classroom_api, "CLIENTE", tmp_path / "classroom_client.json")
    assert classroom_api.archivo_cliente() is None
    web = tmp_path / "client_secret_123.apps.googleusercontent.com.json"
    web.write_text(_json.dumps({"web": {"client_id": "x"}}))
    assert classroom_api.archivo_cliente() == web
    listo, motivo = classroom_api.disponible()
    if "librerías" not in motivo:  # sin las librerías de Google se detiene antes
        assert not listo and "App de escritorio" in motivo
        web.write_text(_json.dumps({"installed": {"client_id": "x"}}))
        assert classroom_api.disponible() == (True, "")


def test_acepta_el_nombre_anterior_del_permiso_de_tareas():
    nuevo = "https://www.googleapis.com/auth/classroom.coursework.students.readonly"
    anterior = "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly"
    concedidos = [anterior if p == nuevo else p for p in classroom_api.PERMISOS]
    assert classroom_api.permisos_faltantes(concedidos) == []
    assert classroom_api.permisos_faltantes(concedidos[:-1]) == [classroom_api.PERMISOS[-1]]
