from proxy.validator import validate_response

SCHEMA = {
    "type": "object",
    "required": ["status", "value"],
    "properties": {
        "status": {"type": "string"},
        "value": {"type": "number"}
    }
}

def test_valid_response_passes():
    result = validate_response({"status": "ok", "value": 42}, SCHEMA)
    assert result.ok
    assert result.errors == []

def test_missing_required_field_fails():
    result = validate_response({"status": "ok"}, SCHEMA)
    assert not result.ok
    assert any("value" in e for e in result.errors)

def test_wrong_type_fails():
    result = validate_response({"status": "ok", "value": "not a number"}, SCHEMA)
    assert not result.ok

def test_no_schema_configured_passes():
    result = validate_response({"anything": "goes"}, {})
    assert result.ok
