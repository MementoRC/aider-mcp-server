"""
Comprehensive tests for the OperationRiskAssessor.

Covers:
- Model and model/operation risk
- File count risk scaling
- Complexity risk analysis
- Historical risk patterns
- Edge cases and error handling
"""

import pytest

from aider_mcp_server.atoms.utils.operation_risk_assessor import (
    OperationRiskAssessor,
    RiskLevel,
)


@pytest.fixture
def assessor():
    return OperationRiskAssessor()


def test_model_risk_base(assessor):
    # gemini should have higher base risk than gpt-4
    result = assessor.assess_operation_risk(
        model="gemini",
        operation_type="bugfix",
        file_count=1,
        operation_params={},
        operation_history=[],
    )
    assert any(f.name == "model_risk" and f.score == 4 for f in result.factors)
    assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)


def test_model_operation_combo_risk(assessor):
    # gemini + architect triggers combo risk
    result = assessor.assess_operation_risk(
        model="gemini",
        operation_type="architect",
        file_count=1,
        operation_params={},
        operation_history=[],
    )
    assert any(f.name == "model_operation_combo" for f in result.factors)
    assert result.total_score > 4
    assert result.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)


def test_file_count_risk_scaling(assessor):
    # 1 file = 0, 5 files = 2, 15 files = 4, 30 files = 6
    for count, expected in [(1, 0), (5, 2), (15, 4), (30, 6)]:
        result = assessor.assess_operation_risk(
            model="gpt-4",
            operation_type="bugfix",
            file_count=count,
            operation_params={},
            operation_history=[],
        )
        file_risk = next(f for f in result.factors if f.name == "file_count_risk")
        assert file_risk.score == expected


def test_complexity_risk_basic(assessor):
    # architect is highest, refactor is medium, bugfix is low
    for op_type, expected in [("architect", 5), ("refactor", 3), ("bugfix", 1)]:
        result = assessor.assess_operation_risk(
            model="gpt-4",
            operation_type=op_type,
            file_count=1,
            operation_params={},
            operation_history=[],
        )
        comp_risk = next(f for f in result.factors if f.name == "complexity_risk")
        assert comp_risk.score == expected


def test_complexity_risk_with_params(assessor):
    # deep_refactor and cross_module increase risk
    params = {"deep_refactor": True, "cross_module": True}
    result = assessor.assess_operation_risk(
        model="gpt-4",
        operation_type="refactor",
        file_count=1,
        operation_params=params,
        operation_history=[],
    )
    comp_risk = next(f for f in result.factors if f.name == "complexity_risk")
    assert comp_risk.score == 3 + 2 + 2  # base + deep_refactor + cross_module
    assert comp_risk.details.get("deep_refactor")
    assert comp_risk.details.get("cross_module")


def test_complexity_risk_experimental(assessor):
    params = {"experimental": True}
    result = assessor.assess_operation_risk(
        model="gpt-4",
        operation_type="add_feature",
        file_count=1,
        operation_params=params,
        operation_history=[],
    )
    comp_risk = next(f for f in result.factors if f.name == "complexity_risk")
    assert comp_risk.score == 2 + 3  # base + experimental
    assert comp_risk.details.get("experimental")


def test_historical_risk_none(assessor):
    # No history, no risk
    result = assessor.assess_operation_risk(
        model="gpt-4",
        operation_type="bugfix",
        file_count=1,
        operation_params={},
        operation_history=[],
    )
    assert not any(f.name == "historical_risk" for f in result.factors)


def test_historical_risk_recent_failures(assessor):
    # 3 recent failures triggers risk
    history = [{"success": False} for _ in range(3)]
    result = assessor.assess_operation_risk(
        model="gpt-4",
        operation_type="bugfix",
        file_count=1,
        operation_params={},
        operation_history=history,
    )
    hist = next(f for f in result.factors if f.name == "historical_risk")
    assert hist.score >= 2
    assert hist.details.get("recent_failures") == 3


def test_historical_risk_similar_failures(assessor):
    # 2 similar failures triggers higher risk
    history = [
        {"success": False, "model": "gpt-4", "operation_type": "bugfix"},
        {"success": False, "model": "gpt-4", "operation_type": "bugfix"},
        {"success": True, "model": "gpt-4", "operation_type": "bugfix"},
    ]
    result = assessor.assess_operation_risk(
        model="gpt-4",
        operation_type="bugfix",
        file_count=1,
        operation_params={},
        operation_history=history,
    )
    hist = next(f for f in result.factors if f.name == "historical_risk")
    assert hist.score >= 3
    assert hist.details.get("similar_failures") == 2


def test_risk_level_thresholds(assessor):
    # low: <=3, medium: 4-7, high: 8-10, critical: >10
    # low
    result = assessor.assess_operation_risk(
        model="gpt-3.5",
        operation_type="bugfix",
        file_count=1,
        operation_params={},
        operation_history=[],
    )
    assert result.risk_level == RiskLevel.LOW

    # medium
    result = assessor.assess_operation_risk(
        model="gpt-4",
        operation_type="refactor",
        file_count=5,
        operation_params={},
        operation_history=[],
    )
    assert result.risk_level == RiskLevel.MEDIUM

    # high
    result = assessor.assess_operation_risk(
        model="gemini",
        operation_type="feature",
        file_count=8,
        operation_params={},
        operation_history=[],
    )
    assert result.risk_level == RiskLevel.HIGH

    # critical
    result = assessor.assess_operation_risk(
        model="gemini",
        operation_type="architect",
        file_count=30,
        operation_params={"experimental": True},
        operation_history=[{"success": False} for _ in range(5)],
    )
    assert result.risk_level == RiskLevel.CRITICAL


def test_edge_case_unknown_model_and_op(assessor):
    # Unknown model and operation_type should use defaults
    result = assessor.assess_operation_risk(
        model="unknown_model",
        operation_type="unknown_op",
        file_count=1,
        operation_params={},
        operation_history=[],
    )
    assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    assert any(f.name == "model_risk" for f in result.factors)
    assert any(f.name == "complexity_risk" for f in result.factors)
