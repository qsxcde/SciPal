"""The use-case layer must import without the heavy RAG stack.

CI installs only the light dependency set, so a module-level torch/faiss import
in application/ would make most tests uncollectable and hide real failures.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_SRC = Path(__file__).resolve().parents[1] / "backend" / "src"

PROBE = '''
import importlib.abc, sys
BLOCK = {"torch", "faiss", "sentence_transformers", "modelscope", "openai", "httpx", "numpy"}

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in BLOCK:
            raise ImportError('blocked: ' + name)
        return None

sys.meta_path.insert(0, Blocker())
import backend.application.documents
import backend.application.indexing
import backend.application.index_maintenance
import backend.application.sessions
print('ok')
'''


@pytest.mark.unit
def test_application_modules_import_without_rag_dependencies(tmp_path):
    script = tmp_path / "probe.py"
    script.write_text(PROBE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(BACKEND_SRC)}

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    assert "ok" in result.stdout
