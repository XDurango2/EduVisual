"""Conectores ("plugins") de actividades calificadas.

Cada conector lee una fuente externa (Google Classroom, y en el futuro Moodle, Blackboard, etc.) y entrega
lo mismo: una `Lectura` con las actividades encontradas y una entrega por alumno y actividad. De ahí en
adelante todas las fuentes siguen el mismo camino (core.actividades): validación fila por fila, conversión
de la calificación al nivel del Atributo de Egreso y registro en la bitácora de cargas.

EduVisual no califica: sólo procesa actividades que el docente ya calificó.

Para agregar un conector nuevo: crear un módulo en esta carpeta con una función que devuelva una `Lectura`
y registrarlo en `CONECTORES_DE_ARCHIVO`.
"""
from dataclasses import dataclass, field


@dataclass
class Lectura:
    origen: str                                       # "classroom", "moodle", ...
    actividades: list[dict] = field(default_factory=list)  # {"nombre", "puntos", "fecha"}
    entregas: list[dict] = field(default_factory=list)     # {"fila", "nombre", "correo", "matricula", "actividad", "valor", "puntos"}


from core.conectores import classroom_csv  # noqa: E402  (después de Lectura para evitar import circular)

# nombre visible -> función(nombre_archivo, contenido) -> Lectura
CONECTORES_DE_ARCHIVO = {
    "Google Classroom (archivo de calificaciones)": classroom_csv.leer,
}
