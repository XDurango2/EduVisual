# EduVisual

Prueba de concepto (Streamlit) para evaluar Atributos de Egreso a partir de evidencias estudiantiles.
El motor sugiere un nivel por indicador con justificación y citas; el docente confirma o corrige.
Además integra calificaciones, resultados CENEVAL y encuestas a empleadores para calcular el nivel de adopción de cada AE.

## Ejecutar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m core.seed        # datos de ejemplo (también se puede desde la app)
streamlit run app.py
```

## Motor de evaluación (local)

- **Ollama (recomendado):** `ollama pull llama3.1:8b` y dejar el servicio activo. Variables opcionales: `OLLAMA_MODEL`, `OLLAMA_URL`.
- **Heurístico:** si Ollama no está disponible, se usa una línea base por palabras clave para que la app siempre funcione.

## Carga de calificaciones, CENEVAL y encuestas a empleadores (RF-001, RF-002, RF-003)

En la página **Carga de datos** se sube un CSV o Excel; cada fila se valida antes de guardarse y la carga
queda en la bitácora con su porcentaje de rechazo (meta del Plan de Calidad: menos de 2%).
La página permite descargar una plantilla de cada formato.

| Fuente | Columnas |
|---|---|
| Calificaciones | `matricula`, `nombre` (sólo alumnos nuevos), `asignatura`, `periodo` (AAAA-N), `calificacion` (0-100) |
| CENEVAL | `matricula`, `nombre` (sólo alumnos nuevos), `examen`, `area`, `periodo` (AAAA-N), `desempeno` (ANS/DS/DSS), `puntaje` (opcional, 700-1300) |
| Encuestas a empleadores | `empleador`, `ae` (id del AE), `periodo` (AAAA-N), `respuesta` (1-5), `consentimiento` (SI/NO) |

Sólo se guardan asignaturas y áreas CENEVAL vinculadas a un AE en `fuentes` de su rúbrica (minimización de datos);
las demás filas se omiten. El formato CENEVAL es preliminar y debe confirmarse con sus encargados.

**Encuestas a empleadores:** cada fila es la valoración (escala Likert 1-5) de un empleador sobre un AE en un periodo.
Sólo se guardan las filas con `consentimiento` SI (las demás se omiten sin almacenarse, como pide el documento de
requerimientos de PI) y cuyo AE tenga `fuentes.encuestas` en su rúbrica. Una fila por empleador, AE y periodo; re-importar
actualiza. La respuesta se convierte a nivel 1-4 con `fuentes.encuestas.escala` y se pondera en el índice de adopción.

`python -m core.seed` también genera en `data/ejemplos/` los archivos `calificaciones_ejemplo.csv`,
`ceneval_ejemplo.csv` y `calificaciones_con_errores.csv` (este último para demostrar la validación).

## Rúbricas

Cada rúbrica en `data/rubricas/` se valida al cargar la app; si un archivo tiene errores se reporta en la barra
lateral y no se usa. Además de los indicadores, cada rúbrica define:

- `fuentes`: peso de cada fuente en el índice de adopción, asignaturas que tributan al AE con su escala de
  conversión a niveles, examen/áreas CENEVAL con la conversión de su desempeño a niveles, y (opcional) `encuestas`
  con la pregunta y la escala que convierte la respuesta 1-5 a niveles.
- `validacion`: estado de la validación académica (`pendiente`, `en revision` o `validada`), quién la validó y cuándo.

## Pruebas

```bash
pip install pytest pytest-cov
python -m pytest --cov=core tests/
```

## Estructura

- `app.py` y `pages/`: interfaz (captura, revisión, panel, reportes).
- `core/`: base de datos SQLite, rúbricas, extracción de texto, evaluador, importación de fuentes
  (`importacion.py`), cálculo de adopción (`adopcion.py`) y datos de ejemplo.
- `tests/`: pruebas automatizadas con pytest.
- `data/rubricas/`: rúbricas por AE en JSON.
- `data/ejemplos/`: evidencias de ejemplo generadas, para probar la carga de archivos.
