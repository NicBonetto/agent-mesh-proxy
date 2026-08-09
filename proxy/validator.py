from dataclasses import dataclass
from typing import Any
from jsonschema import Draft7Validator, exceptions as jsonschema_exceptions

@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]

def validate_response(response: Any, schema: dict) -> ValidationResult:
    if not schema:
        return ValidationResult(ok=True, errors=[])

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(response), key=lambda e: e.path)
    if not errors:
        return ValidationResult(ok=True, errors=[])

    return ValidationResult(
        ok=False,
        errors=[f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
    )
