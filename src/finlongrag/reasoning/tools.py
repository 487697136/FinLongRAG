"""Restricted deterministic tools for agent reasoning."""

from __future__ import annotations

import ast
import operator
from decimal import Decimal, InvalidOperation


class SafeCalculator:
    """Evaluate basic arithmetic expressions without executing Python code."""

    _BIN_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
    }
    _UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    def evaluate(self, expression: str) -> Decimal:
        tree = ast.parse(expression, mode="eval")
        return self._eval(tree.body)

    def _eval(self, node: ast.AST) -> Decimal:
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return Decimal(str(node.value))
        if isinstance(node, ast.BinOp) and type(node.op) in self._BIN_OPS:
            left = self._eval(node.left)
            right = self._eval(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ZeroDivisionError("division by zero")
            return Decimal(str(self._BIN_OPS[type(node.op)](left, right)))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._UNARY_OPS:
            return Decimal(str(self._UNARY_OPS[type(node.op)](self._eval(node.operand))))
        raise ValueError(f"unsupported expression node: {type(node).__name__}")


def compare_values(left: str, right: str) -> str:
    left_value = _decimal(left)
    right_value = _decimal(right)
    if left_value > right_value:
        return "gt"
    if left_value < right_value:
        return "lt"
    return "eq"


def growth_rate(current: str, previous: str) -> Decimal:
    current_value = _decimal(current)
    previous_value = _decimal(previous)
    if previous_value == 0:
        raise ZeroDivisionError("previous value is zero")
    return (current_value - previous_value) / abs(previous_value)


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "").replace("，", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {value}") from exc
