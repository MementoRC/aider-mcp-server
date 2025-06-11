"""
OperationRiskAssessor for Aider Safety Operations.

Evaluates the risk of an operation based on model reliability, file count,
operation complexity, and historical patterns. Returns a structured risk
assessment for use by the safety system.

Author: Aider MCP Server Team
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from aider_mcp_server.atoms.logging.logger import get_logger

logger = get_logger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskFactor:
    name: str
    score: int
    description: str
    details: Optional[Dict[str, Any]] = field(default_factory=dict)


@dataclass
class OperationRiskAssessment:
    total_score: int
    risk_level: RiskLevel
    factors: List[RiskFactor]
    summary: str


class OperationRiskAssessor:
    """
    Assesses the risk of an operation for the Aider Safety System.

    Usage:
        assessor = OperationRiskAssessor()
        assessment = assessor.assess_operation_risk(
            model="gemini",
            operation_type="architect",
            file_count=12,
            operation_params={"refactor": True},
            operation_history=[...]
        )
    """

    # Known problematic model/operation combinations
    _problematic_models = {
        ("gemini", "architect"): 6,
        ("gpt-4", "architect"): 3,
        ("gemini", "refactor"): 4,
    }

    # Model reliability base risk
    _model_risk = {
        "gemini": 4,
        "gpt-4": 2,
        "gpt-3.5": 1,
        "claude": 2,
        "mistral": 2,
    }

    # Complexity risk by operation type
    _complexity_risk = {
        "architect": 5,
        "refactor": 3,
        "add_feature": 2,
        "bugfix": 1,
        "format": 0,
    }

    def __init__(self):
        self.logger = logger

    def assess_operation_risk(
        self,
        model: str,
        operation_type: str,
        file_count: int,
        operation_params: Optional[Dict[str, Any]] = None,
        operation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> OperationRiskAssessment:
        """
        Assess the risk of an operation.

        Args:
            model: Name of the AI model used.
            operation_type: Type of operation (e.g., 'architect', 'refactor').
            file_count: Number of files affected.
            operation_params: Additional operation parameters.
            operation_history: List of past operation dicts (may include 'success', 'failure', etc).

        Returns:
            OperationRiskAssessment object.
        """
        factors: List[RiskFactor] = []
        total_score = 0

        # 1. Model risk (base + problematic combos)
        model_key = model.lower()
        op_key = operation_type.lower()
        model_risk_score = self._model_risk.get(model_key, 2)
        factors.append(RiskFactor(
            name="model_risk",
            score=model_risk_score,
            description=f"Base risk for model '{model_key}'",
        ))
        total_score += model_risk_score

        combo_score = self._problematic_models.get((model_key, op_key), 0)
        if combo_score > 0:
            factors.append(RiskFactor(
                name="model_operation_combo",
                score=combo_score,
                description=f"Known problematic combination: {model_key} + {op_key}",
            ))
            total_score += combo_score

        # 2. File count risk scaling
        if file_count <= 3:
            file_risk = 0
        elif file_count <= 10:
            file_risk = 2
        elif file_count <= 25:
            file_risk = 4
        else:
            file_risk = 6
        factors.append(RiskFactor(
            name="file_count_risk",
            score=file_risk,
            description=f"Risk based on {file_count} files affected",
        ))
        total_score += file_risk

        # 3. Complexity risk
        complexity_score = self._complexity_risk.get(op_key, 2)
        complexity_details = {}
        if operation_params:
            # Increase risk for certain params
            if operation_params.get("deep_refactor"):
                complexity_score += 2
                complexity_details["deep_refactor"] = True
            if operation_params.get("cross_module"):
                complexity_score += 2
                complexity_details["cross_module"] = True
            if operation_params.get("experimental"):
                complexity_score += 3
                complexity_details["experimental"] = True
        factors.append(RiskFactor(
            name="complexity_risk",
            score=complexity_score,
            description=f"Complexity risk for operation type '{op_key}'",
            details=complexity_details,
        ))
        total_score += complexity_score

        # 4. Historical risk
        history_score, history_details = self._analyze_history(operation_history, model_key, op_key)
        if history_score > 0:
            factors.append(RiskFactor(
                name="historical_risk",
                score=history_score,
                description="Elevated risk due to past failures or patterns",
                details=history_details,
            ))
            total_score += history_score

        # 5. Risk level mapping
        if total_score <= 3:
            risk_level = RiskLevel.LOW
        elif total_score <= 7:
            risk_level = RiskLevel.MEDIUM
        elif total_score <= 10:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.CRITICAL

        summary = f"Total risk score: {total_score} ({risk_level.value})"
        self.logger.info(f"Operation risk assessment: {summary}")

        return OperationRiskAssessment(
            total_score=total_score,
            risk_level=risk_level,
            factors=factors,
            summary=summary,
        )

    def _analyze_history(
        self,
        operation_history: Optional[List[Dict[str, Any]]],
        model: str,
        operation_type: str,
    ) -> (int, Dict[str, Any]):
        """
        Analyze operation history for risk patterns.

        Returns:
            (score, details)
        """
        if not operation_history:
            return 0, {}

        recent_failures = 0
        similar_failures = 0
        for op in operation_history[-10:]:
            if op.get("success") is False:
                recent_failures += 1
                if (
                    op.get("model", "").lower() == model
                    and op.get("operation_type", "").lower() == operation_type
                ):
                    similar_failures += 1

        score = 0
        details = {}
        if recent_failures >= 3:
            score += 2
            details["recent_failures"] = recent_failures
        if similar_failures >= 2:
            score += 3
            details["similar_failures"] = similar_failures

        return score, details
