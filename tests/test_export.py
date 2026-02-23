from types import SimpleNamespace

import pytest

pytest.importorskip("openpyxl")
pytest.importorskip("reportlab")

from app.services.export import render_kpi_pdf, render_kpi_xlsx


class Status:
    value = "submitted"


def test_export_files_non_empty():
    metric = SimpleNamespace(template_metric_id=1, fact_value=10, metric_result=100, overtime_result=0)
    instance = SimpleNamespace(
        id=1,
        employee_id=2,
        month="2026-02",
        period_start="2026-02-01",
        period_end="2026-02-28",
        status=Status(),
        overtime_amount=0,
        total_amount=100,
        metrics=[metric],
    )
    assert len(render_kpi_pdf(instance)) > 100
    assert len(render_kpi_xlsx(instance)) > 100
