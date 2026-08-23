import json
import os
from pathlib import Path
import subprocess
import shutil
from tempfile import TemporaryDirectory
from typing import Any, Callable

from backend.domain.config import data_dir
from backend.domain.config import settings
from backend.rag.ingestion.parser_backend import RawParserResult
from backend.domain.config import mineru_model_dir
from backend.domain.config import mineru_modelscope_cache_dir


class MinerUBackend:
    name = "mineru"
    version = "unknown"
    INSTALL_HINT = "Install MinerU runtime and ModelScope dependencies in requirements.txt."

    def __init__(self, parse_runner: Callable[[str, str, str], Any] | None = None):
        self.parse_runner = parse_runner or self._default_parse_runner
        self.disable_ocr = settings.mineru_disable_ocr
        self.runtime_env: dict[str, str] = {}

    def _configure_runtime_env(self, device_override: str | None = None) -> None:
        device = device_override or settings.mineru_torch_device
        model_source, config_file = _resolve_mineru_model_source()
        self.runtime_env = {
            "MINERU_MODEL_HOME": str(mineru_model_dir()),
            "MINERU_MODEL_SOURCE": model_source,
            "MINERU_DEVICE_MODE": device,
            "MODELSCOPE_CACHE": str(mineru_modelscope_cache_dir()),
            "MINERU_TABLE_ENABLE": str(settings.mineru_table_enable).lower(),
            "MINERU_FORMULA_ENABLE": str(settings.mineru_formula_enable).lower(),
        }
        if config_file is not None:
            self.runtime_env["MINERU_TOOLS_CONFIG_JSON"] = str(config_file)
        if self.disable_ocr:
            self.runtime_env["MINERU_DISABLE_OCR"] = "1"

    def parse(self, pdf_bytes: bytes, filename: str | None = None) -> RawParserResult:
        incomplete_cache = _incomplete_local_pipeline_model_root()
        if incomplete_cache is not None:
            raise RuntimeError(
                "MinerU local model cache is incomplete: "
                f"{incomplete_cache}. Re-download matching MinerU pipeline weights "
                "or use the text PDF fallback for copyable PDFs."
            )
        try:
            return self._parse_with_device(pdf_bytes, filename=filename)
        except Exception as exc:
            if not self._should_retry_on_cpu(exc):
                raise self._wrap_runtime_error(exc) from exc
            return self._parse_with_device(pdf_bytes, filename=filename, device_override="cpu")

    def _parse_with_device(
        self,
        pdf_bytes: bytes,
        filename: str | None = None,
        device_override: str | None = None,
    ) -> RawParserResult:
        self._configure_runtime_env(device_override=device_override)
        suffix = Path(filename or "document.pdf").suffix or ".pdf"
        device = device_override or settings.mineru_torch_device
        with TemporaryDirectory() as work_dir, TemporaryDirectory() as output_dir:
            pdf_path = Path(work_dir) / f"input{suffix}"
            pdf_path.write_bytes(pdf_bytes)
            raw_output = self.parse_runner(str(pdf_path), output_dir, device)
        return self._map_raw_output(raw_output)

    def _default_parse_runner(self, pdf_path: str, output_dir: str, device: str) -> dict[str, Any]:
        command = [
            "mineru",
            "-p",
            pdf_path,
            "-o",
            output_dir,
            "-b",
            "pipeline",
        ]
        env = os.environ.copy()
        model_source, config_file = _resolve_mineru_model_source()
        env["MINERU_MODEL_SOURCE"] = model_source
        env["MINERU_DEVICE_MODE"] = device
        env["MODELSCOPE_CACHE"] = str(mineru_modelscope_cache_dir())
        env["MINERU_TABLE_ENABLE"] = str(settings.mineru_table_enable).lower()
        env["MINERU_FORMULA_ENABLE"] = str(settings.mineru_formula_enable).lower()
        if config_file is not None:
            env["MINERU_TOOLS_CONFIG_JSON"] = str(config_file)
        if self.disable_ocr:
            env["MINERU_DISABLE_OCR"] = "1"
        try:
            completed = subprocess.run(
                command,
                **self._subprocess_run_kwargs(env),
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"MinerU parsing timed out after 600s. "
                f"PDF may be too complex or corrupted. "
                f"Falling back to TextPDFBackend."
            ) from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "mineru command failed"
            raise RuntimeError(message)
        markdown = self._read_first_markdown(output_dir)
        metadata = {}
        if not settings.mineru_show_download_progress:
            metadata["stdout"] = completed.stdout.strip()
        return {
            "markdown": markdown,
            "pages": [],
            "metadata": metadata,
        }

    def _subprocess_run_kwargs(self, env: dict[str, str]) -> dict[str, Any]:
        run_kwargs: dict[str, Any] = {
            "check": False,
            "text": True,
            "env": env,
        }
        if not settings.mineru_show_download_progress:
            run_kwargs["capture_output"] = True
        return run_kwargs

    def _read_first_markdown(self, output_dir: str) -> str:
        markdown_files = sorted(Path(output_dir).rglob("*.md"))
        if not markdown_files:
            return ""
        return markdown_files[0].read_text(encoding="utf-8")

    def _should_retry_on_cpu(self, exc: Exception) -> bool:
        configured = (settings.mineru_torch_device or "").lower()
        if configured != "mps":
            return False
        message = str(exc).lower()
        return "mps" in message or "metal" in message

    def _wrap_runtime_error(self, exc: Exception) -> RuntimeError:
        if isinstance(exc, RuntimeError) and "MinerU runtime" in str(exc):
            return exc
        return RuntimeError(
            f"MinerU runtime is unavailable in this environment: {exc}. {self.INSTALL_HINT}"
        )

    def _map_raw_output(self, raw_output: Any) -> RawParserResult:
        if isinstance(raw_output, RawParserResult):
            return raw_output.model_copy(update={"source_parser": self.name})
        if isinstance(raw_output, str):
            output: dict[str, Any] = json.loads(raw_output)
        elif hasattr(raw_output, "model_dump"):
            output = raw_output.model_dump()
        else:
            output = raw_output
        markdown = str(output.get("markdown", "")) if isinstance(output, dict) else ""
        pages = output.get("pages", []) if isinstance(output, dict) else []
        metadata = output.get("metadata", {}) if isinstance(output, dict) else {}
        warnings = output.get("warnings", []) if isinstance(output, dict) else []
        return RawParserResult(
            markdown=markdown,
            page_count=len(pages),
            pages=pages,
            metadata=metadata,
            source_parser=self.name,
            warnings=list(warnings),
        )


def _resolve_mineru_model_source() -> tuple[str, Path | None]:
    pipeline_root = _local_pipeline_model_root()
    if pipeline_root is None:
        return "modelscope", None
    config_path = _ensure_local_mineru_config(pipeline_root)
    return "local", config_path


def _local_pipeline_model_root() -> Path | None:
    candidates = [
        mineru_model_dir() / "pipeline",
        mineru_modelscope_cache_dir() / "models" / "OpenDataLab" / "PDF-Extract-Kit-1___0",
    ]
    for candidate in candidates:
        if _looks_like_pipeline_model_root(candidate):
            return candidate
    return None


def _incomplete_local_pipeline_model_root() -> Path | None:
    candidate = mineru_modelscope_cache_dir() / "models" / "OpenDataLab" / "PDF-Extract-Kit-1___0"
    if candidate.exists() and not _looks_like_pipeline_model_root(candidate):
        return candidate
    return None


def _looks_like_pipeline_model_root(path: Path) -> bool:
    models_dir = path / "models"
    if not models_dir.exists():
        return False
    ocr_dir = models_dir / "OCR" / "paddleocr_torch"
    if ocr_dir.exists() and not any(ocr_dir.glob("*.pth")):
        return False
    return (
        (models_dir / "MFR").exists()
        or (models_dir / "Layout").exists()
        or (models_dir / "OCR").exists()
    )


def _ensure_local_mineru_config(pipeline_root: Path) -> Path:
    config_path = data_dir() / "mineru.json"
    config_path.write_text(
        json.dumps(
            {
                "models-dir": {
                    "pipeline": str(pipeline_root),
                    "vlm": str(pipeline_root),
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return config_path
