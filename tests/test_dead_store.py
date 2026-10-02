import ast

import pytest

from analyzer.rules.dead_store import DeadStoreRule


def _lines(src: str) -> list[int]:
    return [f.line for f in DeadStoreRule().check(ast.parse(src))]


def test_overwritten_on_every_branch():
    src = "def f(c):\n    x = g()\n    if c:\n        x = 1\n    else:\n        x = 2\n    return x\n"
    assert _lines(src) == [2]


def test_straight_line_overwrite():
    assert _lines("def f():\n    y = g()\n    y = h()\n    return y\n") == [2]


def test_overwrite_inside_loop_body():
    src = "def f(xs):\n    for x in xs:\n        v = g(x)\n        v = h(x)\n        print(v)\n"
    assert _lines(src) == [3]


def test_overwritten_by_walrus():
    assert _lines("def f():\n    n = g()\n    if (n := h()):\n        return n\n") == [2]


def test_overwritten_by_with_target():
    assert _lines("def f():\n    fh = g()\n    with open('a') as fh:\n        return fh.read()\n") == [2]


def test_overwritten_by_match_capture():
    src = (
        "def f(p):\n    v = g()\n    match p:\n        case [v]:\n            return v\n"
        "        case _:\n            return 0\n"
    )
    assert _lines(src) == [2]


@pytest.mark.parametrize(
    "src",
    [
        # read on at least one path
        "def f(c):\n    x = g()\n    if c:\n        x = 1\n    return x\n",
        # loop-carried values
        "def f(xs):\n    t = g()\n    for x in xs:\n        t = t + x\n    return t\n",
        "def f():\n    i = g()\n    while i < 10:\n        i = i + 1\n    return i\n",
        "def f(xs):\n    for x in xs:\n        last = x * 2\n    return last\n",
        # an exception handler / finally may observe the earlier value
        "def f():\n    x = g()\n    try:\n        x = h()\n    except E:\n        return x\n    return x\n",
        "def f():\n    x = g()\n    try:\n        x = h()\n        return 1\n"
        "    finally:\n        print(x)\n",
        # read by a closure
        "def f():\n    x = g()\n    def inner():\n        return x\n    x = h()\n    return inner\n",
        # not a local
        "def f():\n    global x\n    x = g()\n    x = h()\n",
        # dynamic access to the frame
        "def f():\n    x = g()\n    x = h()\n    return locals()\n",
        # default-value initialization idiom
        "def f(c):\n    r = None\n    if c:\n        r = 1\n    else:\n        r = 2\n    return r\n",
        # underscore-prefixed
        "def f():\n    _x = g()\n    _x = h()\n    return _x\n",
        # never read at all: unused-variable's job, not reported twice
        "def f():\n    x = g()\n    x = h()\n",
        # module and class scopes are not checked
        "x = g()\nx = h()\nprint(x)\n",
        "class C:\n    x = g()\n    x = h()\n    y = x\n",
        # tuple unpacking is not checked
        "def f():\n    a, b = g()\n    a = h()\n    return a, b\n",
    ],
)
def test_not_a_dead_store(src):
    assert _lines(src) == []


def test_store_in_unreachable_code_is_left_to_dead_code():
    assert _lines("def f():\n    return 1\n    x = g()\n    x = h()\n    return x\n") == []
