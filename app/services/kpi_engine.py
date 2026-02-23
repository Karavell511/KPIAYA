import ast
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import KPIInstance, KPITemplate, KPITemplateMetric

_ALLOWED_FUNCS = {"min": min, "max": max, "round": round, "Decimal": Decimal}
_ALLOWED_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
_ALLOWED_UNARY_OPS = (ast.UAdd, ast.USub)


class FormulaValidationError(ValueError):
    pass


class _SafeFormulaEvaluator(ast.NodeVisitor):
    def __init__(self, context: dict[str, Decimal]) -> None:
        self.context = context

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_Name(self, node: ast.Name):
        if node.id in self.context:
            return self.context[node.id]
        if node.id in _ALLOWED_FUNCS:
            return _ALLOWED_FUNCS[node.id]
        raise FormulaValidationError(f"Unknown symbol: {node.id}")

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, (int, float, str)):
            return Decimal(str(node.value)) if not isinstance(node.value, str) else Decimal(node.value)
        raise FormulaValidationError("Unsupported constant type")

    def visit_BinOp(self, node: ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BIN_OPS):
            raise FormulaValidationError("Unsupported binary operator")
        left = Decimal(str(self.visit(node.left)))
        right = Decimal(str(self.visit(node.right)))
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return Decimal("0") if right == 0 else left / right
        if isinstance(node.op, ast.Pow):
            return left**right
        if isinstance(node.op, ast.Mod):
            return left % right
        raise FormulaValidationError("Unsupported binary operation")

    def visit_UnaryOp(self, node: ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARY_OPS):
            raise FormulaValidationError("Unsupported unary operator")
        value = Decimal(str(self.visit(node.operand)))
        return value if isinstance(node.op, ast.UAdd) else -value

    def visit_Call(self, node: ast.Call):
        func = self.visit(node.func)
        args = [self.visit(arg) for arg in node.args]
        if func not in _ALLOWED_FUNCS.values():
            raise FormulaValidationError("Function is not allowed")
        return func(*args)

    def generic_visit(self, node):
        raise FormulaValidationError(f"Disallowed AST node: {type(node).__name__}")


def validate_formula(formula: str) -> None:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise FormulaValidationError("Formula syntax error") from exc
    _SafeFormulaEvaluator(
        {
            "max_total_amount": Decimal("1"),
            "weight_percent": Decimal("1"),
            "plan_value": Decimal("1"),
            "fact_value": Decimal("1"),
            "max_metric_amount": Decimal("1"),
        }
    ).visit(tree)


def evaluate_formula(formula: str, context: dict[str, Decimal]) -> Decimal:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise FormulaValidationError("Formula syntax error") from exc
    value = _SafeFormulaEvaluator(context).visit(tree)
    return Decimal(str(value))


def salary_components(base_salary: Decimal, salary_share_percent: Decimal, overtime_hours_x1: Decimal, overtime_hours_x2: Decimal) -> dict[str, Decimal]:
    salary_kpi_amount = base_salary * (salary_share_percent / Decimal("100"))
    hourly_rate = Decimal("0") if settings.working_hours_per_month == 0 else base_salary / Decimal(str(settings.working_hours_per_month))
    overtime_x1_amount = overtime_hours_x1 * hourly_rate * Decimal(str(settings.overtime_multiplier_x1))
    overtime_x2_amount = overtime_hours_x2 * hourly_rate * Decimal(str(settings.overtime_multiplier_x2))
    return {
        "salary_kpi_amount": salary_kpi_amount,
        "hourly_rate": hourly_rate,
        "overtime_x1_amount": overtime_x1_amount,
        "overtime_x2_amount": overtime_x2_amount,
        "overtime_total": overtime_x1_amount + overtime_x2_amount,
    }


async def calculate_instance(session: AsyncSession, instance: KPIInstance) -> KPIInstance:
    template: KPITemplate = instance.template
    metrics_total = Decimal("0")

    for metric in instance.metrics:
        template_metric = await session.get(KPITemplateMetric, metric.template_metric_id)
        if not template_metric:
            raise FormulaValidationError(f"Template metric #{metric.template_metric_id} not found")

        max_metric_amount = Decimal(str(template.max_total_amount)) * (Decimal(str(template_metric.weight_percent)) / Decimal("100"))
        context = {
            "max_total_amount": Decimal(str(template.max_total_amount)),
            "weight_percent": Decimal(str(template_metric.weight_percent)),
            "plan_value": Decimal(str(template_metric.plan_value)),
            "fact_value": Decimal(str(metric.fact_value)),
            "max_metric_amount": max_metric_amount,
        }
        metric.metric_result = evaluate_formula(template_metric.formula, context)
        metrics_total += Decimal(str(metric.metric_result)) + Decimal(str(metric.overtime_result or 0))

    comp = salary_components(
        Decimal(str(instance.base_salary or 0)),
        Decimal(str(instance.salary_share_percent or 0)),
        Decimal(str(instance.overtime_hours_x1 or 0)),
        Decimal(str(instance.overtime_hours_x2 or 0)),
    )
    instance.overtime_amount = comp["overtime_total"]
    instance.total_amount = metrics_total + comp["salary_kpi_amount"] + comp["overtime_total"]
    return instance


async def archive_old_kpis(session: AsyncSession, month: str) -> int:
    query = select(KPIInstance).where(KPIInstance.month < month, KPIInstance.is_archived.is_(False))
    result = await session.execute(query)
    rows = result.scalars().all()
    for item in rows:
        item.is_archived = True
    return len(rows)
