from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core import seed

RAIZ = Path(__file__).resolve().parent.parent
PAGINAS = ["app.py"] + sorted(f"pages/{p.name}" for p in (RAIZ / "pages").glob("*.py"))


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_carga_sin_excepciones_con_datos_de_ejemplo(pagina):
    seed.sembrar()
    at = AppTest.from_file(str(RAIZ / pagina), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
