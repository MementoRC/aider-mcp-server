import pytest

from aider_mcp_server.atoms.utils.model_response_validator import (
    ModelResponseValidator,
    ValidationError,
)


@pytest.fixture
def validator():
    return ModelResponseValidator()


def make_response(
    diff: str = "",
    summary: str = "",
    files: list = None,
    api_key_status: dict = None,
    rate_limit_info: dict = None,
    error: str = "",
):
    resp = {
        "diff": diff,
        "changes_summary": {
            "summary": summary,
            "files": files if files is not None else [],
        },
        "api_key_status": api_key_status or {},
        "rate_limit_info": rate_limit_info or {},
    }
    if error:
        resp["error"] = error
    return resp


def test_complete_response_by_diff(validator):
    resp = make_response(diff="This is a valid diff\nwith changes.", summary="", files=[])
    assert validator.is_response_complete(resp)
    # Should not raise
    validator.validate_response(resp, requested_model="gpt-4")


def test_complete_response_by_summary(validator):
    resp = make_response(diff="", summary="Added new feature implementation.", files=[])
    assert validator.is_response_complete(resp)
    validator.validate_response(resp, requested_model="gpt-4")


def test_complete_response_by_files(validator):
    resp = make_response(diff="", summary="", files=[{"name": "foo.py", "operation": "created"}])
    assert validator.is_response_complete(resp)
    validator.validate_response(resp, requested_model="gpt-4")


def test_incomplete_response_raises(validator):
    resp = make_response(diff="", summary="", files=[])
    assert not validator.is_response_complete(resp)
    with pytest.raises(ValidationError) as exc:
        validator.validate_response(resp, requested_model="gpt-4")
    assert "validation failed" in str(exc.value).lower()


def test_model_consistency_pass(validator):
    resp = make_response(
        diff="This is a long enough diff content for validation", api_key_status={"actual_model_used": "gpt-4"}
    )
    assert validator.is_model_consistent(resp, "gpt-4")
    validator.validate_response(resp, requested_model="gpt-4")


def test_model_consistency_fail_warns(validator):
    resp = make_response(
        diff="This is a long enough diff content for validation", api_key_status={"actual_model_used": "gpt-3.5-turbo"}
    )
    # Should warn, but not raise if allow_fallback=True (default)
    assert not validator.is_model_consistent(resp, "gpt-4")
    validator.validate_response(resp, requested_model="gpt-4", allow_fallback=True)


def test_model_consistency_fail_raises(validator):
    resp = make_response(
        diff="This is a long enough diff content for validation", api_key_status={"actual_model_used": "gpt-3.5-turbo"}
    )
    with pytest.raises(ValidationError) as exc:
        validator.validate_response(resp, requested_model="gpt-4", allow_fallback=False)
    assert "validation failed" in str(exc.value).lower()


def test_detect_api_error_field(validator):
    resp = make_response(diff="This is a long enough diff content for validation", error="API quota exceeded")
    assert validator.detect_api_error(resp) == "API quota exceeded"
    with pytest.raises(ValidationError) as exc:
        validator.validate_response(resp, requested_model="gpt-4")
    assert "validation failed" in str(exc.value).lower()


def test_detect_api_error_rate_limit(validator):
    resp = make_response(
        diff="This is a long enough diff content for validation", rate_limit_info={"encountered": True, "retries": 2}
    )
    assert validator.detect_api_error(resp) == "Rate limit encountered"
    with pytest.raises(ValidationError) as exc:
        validator.validate_response(resp, requested_model="gpt-4")
    assert "validation failed" in str(exc.value).lower()


def test_detect_fallback_by_actual_model(validator):
    resp = make_response(
        diff="This is a long enough diff content for validation",
        api_key_status={
            "actual_model_used": "gpt-3.5-turbo",
            "used_provider": "openai",
        },
    )
    info = validator.detect_fallback(resp, requested_model="gpt-4")
    assert info
    assert info["used_model"] == "gpt-3.5-turbo"
    assert info["used_provider"] == "openai"
    # Should add warning, not raise
    validator.validate_response(resp, requested_model="gpt-4", allow_fallback=True)
    assert any("fallback" in w.lower() for w in resp.get("warnings", []))


def test_detect_fallback_by_rate_limit_info(validator):
    resp = make_response(
        diff="This is a long enough diff content for validation",
        api_key_status={"used_provider": "openai"},
        rate_limit_info={"fallback_model": "gpt-3.5-turbo"},
    )
    info = validator.detect_fallback(resp, requested_model="gpt-4")
    assert info
    assert info["used_model"] == "gpt-3.5-turbo"
    assert info["used_provider"] == "openai"
    validator.validate_response(resp, requested_model="gpt-4", allow_fallback=True)
    assert any("fallback" in w.lower() for w in resp.get("warnings", []))


def test_no_fallback_when_models_match(validator):
    resp = make_response(
        diff="This is a long enough diff content for validation",
        api_key_status={"actual_model_used": "gpt-4", "used_provider": "openai"},
    )
    info = validator.detect_fallback(resp, requested_model="gpt-4")
    assert info is None
    validator.validate_response(resp, requested_model="gpt-4", allow_fallback=True)
