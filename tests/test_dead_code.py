import ast

from analyzer.rules.dead_code import DeadCodeRule


def _check(src: str):
    return DeadCodeRule().check(ast.parse(src))


def test_after_return():
    f = _check(
        """
def f():
    return 1
    print('x')
"""
    )
    assert len(f) == 1
    assert "return" in f[0].message
    assert f[0].line == 4


def test_after_raise():
    f = _check(
        """
def f():
    raise ValueError('x')
    cleanup()
"""
    )
    assert len(f) == 1 and "raise" in f[0].message


def test_after_break_in_loop():
    f = _check(
        """
def f():
    for i in range(3):
        break
        print('x')
"""
    )
    assert len(f) == 1 and "break" in f[0].message


def test_after_continue_in_loop():
    f = _check(
        """
def f():
    for i in range(3):
        continue
        print('x')
"""
    )
    assert len(f) == 1 and "continue" in f[0].message


def test_clean_function_no_findings():
    assert _check("def f(x):\n    if x:\n        return 1\n    return 2\n") == []


def test_only_first_dead_statement_per_block():
    f = _check(
        """
def f():
    return 1
    a = 2
    b = 3
"""
    )
    assert len(f) == 1


def test_separate_blocks_each_flagged():
    f = _check(
        """
def f(x):
    if x:
        return 1
        print('a')
    else:
        return 2
        print('b')
"""
    )
    assert len(f) == 2


def test_terminal_at_end_is_fine():
    assert _check("def f():\n    return 1\n") == []
