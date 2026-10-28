# EduVisual

Prueba de concepto (Streamlit) para evaluar Atributos de Egreso a partir de evidencias estudiantiles.
El alcance actual es un solo programa educativo (Ingeniería en Computación) con una sola unidad de aprendizaje (UA), Ingeniería de Software, con datos sintéticos para demostración.
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
| Calificaciones | `matricula`, `nombre` (sólo alumnos nuevos), `asignatura` (nombre de la UA), `periodo` (AAAA-N), `calificacion` (0-100) |
| CENEVAL | `matricula`, `nombre` (sólo alumnos nuevos), `examen`, `area`, `periodo` (AAAA-N), `desempeno` (ANS/DS/DSS), `puntaje` (opcional, 700-1300) |
| Encuestas a empleadores | `empleador`, `ae` (id del AE), `periodo` (AAAA-N), `respuesta` (1-5), `consentimiento` (SI/NO) |

Sólo se guardan unidades de aprendizaje y áreas CENEVAL vinculadas a un AE en `fuentes` de su rúbrica (minimización de datos);
las demás filas se omiten. El formato CENEVAL es preliminar y debe confirmarse con sus encargados.

**Encuestas a empleadores:** cada fila es la valoración (escala Likert 1-5) de un empleador sobre un AE en un periodo.
Sólo se guardan las filas con `consentimiento` SI (las demás se omiten sin almacenarse, como pide el documento de
requerimientos de PI) y cuyo AE tenga `fuentes.encuestas` en su rúbrica. Una fila por empleador, AE y periodo; re-importar
actualiza. La respuesta se convierte a nivel 1-4 con `fuentes.encuestas.escala` y se pondera en el índice de adopción.

`python -m core.seed` también genera en `data/ejemplos/` los archivos `calificaciones_ejemplo.csv`,
`ceneval_ejemplo.csv` y `calificaciones_con_errores.csv` (este último para demostrar la validación).

## Encuestas de empleadores y egresados

Tercera pestaña de **Carga de datos**. Las encuestas son anónimas (`respondente` es un folio, no una matrícula):

| Fuente | Columnas |
|---|---|
| Encuestas | `tipo` (empleador/egresado), `respondente`, `ae_id`, `periodo` (AAAA-N), `valoracion` (1-4), `comentario` (opcional) |

La valoración usa la escala 1-4 de las rúbricas y entra al índice de adopción con el peso de `fuentes.encuestas`.
El formato es preliminar y debe confirmarse con quien aplica las encuestas.

## Reportes y resumen preliminar

- **Reportes** descarga un libro Excel consolidado y un PDF con el resumen y las tablas agregadas. El Excel trae resumen, adopción por fuente, por alumno, por UA, detalle,
  encuestas y bitácora. El formato es genérico; todavía no sigue una cédula oficial de CACEI.
- El **resumen preliminar** (Panel y Reportes) se redacta con reglas a partir de las métricas; no usa el LLM.

## Rúbricas

Si hay más de una rúbrica válida, la barra lateral muestra un selector de Atributo de Egreso que se conserva entre páginas.

Cada rúbrica en `data/rubricas/` se valida al cargar la app; si un archivo tiene errores se reporta en la barra
lateral y no se usa. Además de los indicadores, cada rúbrica define:

- `fuentes`: peso de cada fuente en el índice de adopción, unidades de aprendizaje (clave `asignaturas`) que tributan al AE con su
  escala de conversión a niveles, examen/áreas CENEVAL con la conversión de su desempeño a niveles, y (opcional) `encuestas`
  con la pregunta, los tipos de respondente (`empleador`, `egresado`) y la escala que convierte la respuesta 1-5 a niveles.
- `formato_oficial`: código del formato de la cédula de valoración de AE y la equivalencia de los 4 niveles a los grados
  oficiales NS / SA / SO (por defecto 1-2 → NS, 3 → SA, 4 → SO).
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
