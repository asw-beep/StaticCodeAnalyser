import ast

from analyzer.rules.unused_variable import UnusedVariableRule


def _check(src: str):
    return UnusedVariableRule().check(ast.parse(src))


def test_flags_simple_unused_local():
    findings = _check(
        """
def f():
    x = 1
    y = 2
    return y
"""
    )
    names = [f.message for f in findings]
    assert any("'x'" in n for n in names)
    assert not any("'y'" in n for n in names)


def test_function_parameters_are_exempt():
    findings = _check("def f(a, b, *args, **kw):\n    return 0\n")
    assert findings == []


def test_loop_variable_is_exempt():
    findings = _check(
        """
def f(items):
    for i in items:
        print('tick')
"""
    )
    assert findings == []


def test_underscore_prefix_is_exempt():
    findings = _check("def f():\n    _unused = 1\n    return 0\n")
    assert findings == []


def test_aug_assign_is_not_flagged():
    findings = _check(
        """
def f():
    total = 0
    for i in range(3):
        total += i
    return total
"""
    )
    assert findings == []


def test_closure_use_counts_as_used():
    findings = _check(
        """
def outer():
    x = 10
    def inner():
        return x
    return inner
"""
    )
    # x is used by inner; outer's `inner` is returned (used).
    assert findings == []


def test_module_level_unused_is_flagged():
    findings = _check("CONST = 1\nUSED = 2\nprint(USED)\n")
    msgs = [f.message for f in findings]
    assert any("'CONST'" in m for m in msgs)


def test_tuple_unpacking_partial_unused():
    findings = _check(
        """
def f():
    a, b = 1, 2
    return a
"""
    )
    msgs = [f.message for f in findings]
    assert any("'b'" in m for m in msgs)
    assert not any("'a'" in m for m in msgs)
