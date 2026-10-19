# EduVisual

Prueba de concepto (Streamlit) para evaluar Atributos de Egreso a partir de evidencias estudiantiles.
El motor sugiere un nivel por indicador con justificación y citas; el docente confirma o corrige.

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

## Estructura

- `app.py` y `pages/`: interfaz (captura, revisión, panel, reportes).
- `core/`: base de datos SQLite, rúbricas, extracción de texto, evaluador y datos de ejemplo.
- `data/rubricas/`: rúbricas por AE en JSON.
- `data/ejemplos/`: evidencias de ejemplo generadas, para probar la carga de archivos.
