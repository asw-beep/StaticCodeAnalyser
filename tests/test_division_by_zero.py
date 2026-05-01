import ast

from analyzer.rules.division_by_zero import DivisionByZeroRule


def _check(src: str):
    return DivisionByZeroRule().check(ast.parse(src))


def test_literal_zero_divisor_is_error():
    f = _check("def f():\n    return 10 / 0\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_floor_div_by_zero_is_error():
    f = _check("def f():\n    return 10 // 0\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_modulo_by_zero_is_error():
    f = _check("def f():\n    return 10 % 0\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_zero_float_is_error():
    f = _check("def f():\n    return 1 / 0.0\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_variable_divisor_is_info():
    f = _check("def f(x):\n    return 10 / x\n")
    assert len(f) == 1 and f[0].severity == "INFO"


def test_safe_constant_divisor_still_info():
    # We don't try to prove safety; non-zero literal divisors don't reach this branch.
    f = _check("def f():\n    return 10 / 2\n")
    assert f == []


def test_name_always_zero_is_error():
    f = _check(
        """
def f():
    z = 0
    return 10 / z
"""
    )
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_name_assigned_nonzero_is_info():
    f = _check(
        """
def f():
    z = 0
    z = 5
    return 10 / z
"""
    )
    # Mixed assignments -> not provably zero -> INFO.
    assert len(f) == 1 and f[0].severity == "INFO"


def test_no_division_no_findings():
    assert _check("def f(a, b):\n    return a + b\n") == []


def test_nested_function_scope_isolated():
    # `z = 0` in outer must not poison inner's view of `z`.
    f = _check(
        """
def outer():
    z = 0
    def inner(z):
        return 10 / z
    return inner
"""
    )
    # Only the inner division should be flagged (INFO — z is a parameter there).
    assert len(f) == 1 and f[0].severity == "INFO"
