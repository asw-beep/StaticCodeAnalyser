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


# --- reachability via the control-flow graph ---------------------------------


def _lines_and_messages(src: str):
    return [(f.line, f.message) for f in _check(src)]


def test_after_if_else_where_every_branch_returns():
    src = "def f(c):\n    if c:\n        return 1\n    else:\n        return 2\n    print('dead')\n"
    assert _lines_and_messages(src) == [(6, "Unreachable code: every path through the preceding 'if' exits")]


def test_after_infinite_loop_without_break():
    src = "def f():\n    while True:\n        step()\n    print('dead')\n"
    assert _lines_and_messages(src) == [(4, "Unreachable code after infinite loop")]


def test_infinite_loop_with_break_is_fine():
    assert _check("def f(c):\n    while True:\n        if c:\n            break\n    print('ok')\n") == []


def test_after_sys_exit():
    src = "import sys\ndef f():\n    sys.exit(1)\n    print('dead')\n"
    assert _lines_and_messages(src) == [(4, "Unreachable code after 'sys.exit()'")]


def test_if_false_body_is_dead():
    src = "def f():\n    if False:\n        debug()\n    run()\n"
    assert _lines_and_messages(src) == [(3, "Unreachable code: condition is always false")]


def test_try_with_falling_through_handler_is_fine():
    src = "def f():\n    try:\n        return g()\n    except E:\n        pass\n    print('ok')\n"
    assert _check(src) == []


def test_after_try_where_body_and_handlers_all_exit():
    src = "def f():\n    try:\n        return g()\n    except E:\n        return 2\n    print('dead')\n"
    assert [ln for ln, _ in _lines_and_messages(src)] == [6]


def test_after_try_finally_whose_body_returns():
    src = "def f():\n    try:\n        return 1\n    finally:\n        close()\n    print('dead')\n"
    assert [ln for ln, _ in _lines_and_messages(src)] == [6]


def test_with_block_may_swallow_exceptions():
    # contextlib.suppress-style managers can resume after the block.
    assert _check("def f():\n    with suppress(E):\n        return 1\n    print('ok')\n") == []


def test_after_exhaustive_match():
    src = (
        "def f(x):\n    match x:\n        case 1:\n            return 1\n"
        "        case _:\n            return 2\n    print('dead')\n"
    )
    assert [ln for ln, _ in _lines_and_messages(src)] == [7]


def test_non_exhaustive_match_falls_through():
    assert _check("def f(x):\n    match x:\n        case 1:\n            return 1\n    print('ok')\n") == []


def test_break_through_finally_leaves_loop():
    src = (
        "def f():\n    while True:\n        try:\n            break\n"
        "        finally:\n            c()\n    print('ok')\n"
    )
    assert _check(src) == []


def test_infinite_loop_with_try_finally_and_no_break():
    src = (
        "def f():\n    while True:\n        try:\n            g()\n"
        "        finally:\n            c()\n    print('dead')\n"
    )
    assert _lines_and_messages(src) == [(7, "Unreachable code after infinite loop")]


def test_nested_dead_region_reported_once():
    src = "def f(c):\n    return\n    if c:\n        a()\n        b()\n    d()\n"
    assert [ln for ln, _ in _lines_and_messages(src)] == [3]


def test_module_level_dead_code():
    assert [ln for ln, _ in _lines_and_messages("x = 1\nraise SystemExit\nprint(x)\n")] == [3]
