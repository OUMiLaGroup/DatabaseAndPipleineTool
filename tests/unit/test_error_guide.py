"""Every error code in services/errors.py must be documented in docs/ERROR_GUIDE.md."""
import inspect
from pathlib import Path

from services import errors


def _find_guide() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "ERROR_GUIDE.md"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("docs/ERROR_GUIDE.md not found")


def _error_codes() -> set[str]:
    codes = set()
    for _, cls in inspect.getmembers(errors, inspect.isclass):
        if issubclass(cls, errors.PipelineError) and cls.__module__ == errors.__name__:
            codes.add(cls.code)
    return codes


def test_every_error_code_is_in_the_guide():
    guide = _find_guide().read_text()
    missing = sorted(code for code in _error_codes() if code not in guide)
    assert not missing, f"Add these error codes to docs/ERROR_GUIDE.md: {missing}"


def test_every_error_with_a_status_has_a_hint_or_is_internal():
    # User-facing errors (4xx returned by the API) should tell the user how to fix them
    internal_suffixes = ("_ALREADY_EXISTS",)
    generic = {"PIPELINE_ERROR", "NOT_FOUND", "CONFLICT", "ALREADY_EXISTS"}
    for _, cls in inspect.getmembers(errors, inspect.isclass):
        if not (issubclass(cls, errors.PipelineError) and cls.__module__ == errors.__name__):
            continue
        if cls.code in generic or cls.code.endswith(internal_suffixes):
            continue
        assert cls.hint, f"{cls.__name__} ({cls.code}) has no hint"
