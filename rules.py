"""A small, safe rule-expression evaluator.

Rules are written like:  driver_age < 21 and prior_claims >= 2
Allowed: field names, numbers, quoted text, lists, comparisons (< <= > >= == != in, not in),
and / or / not, and parentheses. Nothing else is executed.
"""
import ast
import operator

_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.Eq: operator.eq, ast.NotEq: operator.ne,
        ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}


class RuleError(ValueError):
    pass


def _prep(text: str) -> str:
    t = text.strip()
    for word, rep in ((" AND ", " and "), (" OR ", " or "), (" NOT ", " not "), (" IN ", " in "), (" = ", " == ")):
        t = t.replace(word, rep)
    return t


def compile_rule(text: str) -> ast.Expression:
    try:
        tree = ast.parse(_prep(text), mode="eval")
    except SyntaxError as exc:
        raise RuleError(f"Can't read this condition near position {exc.offset}.") from None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Compare,
                                 ast.Name, ast.Load, ast.Constant, ast.List, ast.Tuple, ast.USub,
                                 *_CMP.keys())):
            raise RuleError(f"'{type(node).__name__}' isn't allowed in a rule.")
    return tree


def fields_used(tree: ast.Expression) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def evaluate(tree: ast.Expression, record: dict) -> bool:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.BoolOp):
            vals = (ev(v) for v in n.values)
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.UnaryOp):
            return (not ev(n.operand)) if isinstance(n.op, ast.Not) else -ev(n.operand)
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = ev(comp)
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(n, ast.Name):
            if n.id not in record:
                raise RuleError(f"Unknown field '{n.id}'.")
            return record[n.id]
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, (ast.List, ast.Tuple)):
            return [ev(e) for e in n.elts]
        raise RuleError("Unsupported expression.")

    try:
        return bool(ev(tree))
    except TypeError:
        raise RuleError("A comparison mixes text and numbers.") from None
