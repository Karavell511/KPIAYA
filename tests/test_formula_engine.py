import pytest

pytest.importorskip("sqlalchemy")

from decimal import Decimal

import pytest

from app.services.kpi_engine import FormulaValidationError, evaluate_formula, validate_formula


def test_formula_validation_rejects_unsafe_nodes():
    with pytest.raises(FormulaValidationError):
        validate_formula("__import__('os').system('id')")


def test_formula_eval_computes_context_expression():
    result = evaluate_formula(
        "max_metric_amount * (fact_value / plan_value)",
        {
            "max_total_amount": Decimal("36000"),
            "weight_percent": Decimal("50"),
            "plan_value": Decimal("100"),
            "fact_value": Decimal("90"),
            "max_metric_amount": Decimal("18000"),
        },
    )
    assert result == Decimal("16200")
