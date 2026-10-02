"""Direct tests of the CFG builder and liveness, independent of any rule."""

import ast

from analyzer.cfg import build_cfg, live_out


def _fn_body(src: str) -> list[ast.stmt]:
    return ast.parse(src).body[0].body


def _reachable_lines(src: str) -> set[int]:
    cfg = build_cfg(_fn_body(src))
    reach = cfg.reachable()
    return {s.lineno for s, b in cfg.owner_blocks().items() if b in reach}


def test_every_statement_gets_a_block():
    body = _fn_body(
        "def f(x):\n    a = 1\n    if x:\n        pass\n    for i in x:\n        pass\n"
        "    while x:\n        pass\n    with x:\n        pass\n    try:\n        pass\n"
        "    except E:\n        pass\n    match x:\n        case _:\n            pass\n"
    )
    owners = build_cfg(body).owner_blocks()
    stmts = [n for n in ast.walk(ast.Module(body=body, type_ignores=[])) if isinstance(n, ast.stmt)]
    assert all(s in owners for s in stmts)


def test_entry_reaches_exit_for_straight_line_code():
    cfg = build_cfg(_fn_body("def f():\n    a = 1\n    b = 2\n"))
    assert cfg.exit in cfg.reachable()


def test_exit_unreachable_for_infinite_loop():
    cfg = build_cfg(_fn_body("def f():\n    while True:\n        pass\n"))
    assert cfg.exit not in cfg.reachable()


def test_while_else_runs_only_without_break():
    src = "def f():\n    while True:\n        break\n    else:\n        never()\n    after()\n"
    lines = _reachable_lines(src)
    assert 5 not in lines and 6 in lines


def test_handler_reachable_from_try_body():
    lines = _reachable_lines("def f():\n    try:\n        g()\n    except E:\n        h()\n")
    assert 5 in lines


def test_liveness_through_loop_back_edge():
    # `t` is read in the loop body on every iteration, so the value assigned
    # before the loop is live when control leaves the first block.
    body = _fn_body("def f(xs):\n    t = 0\n    for x in xs:\n        t = t + x\n    return t\n")
    cfg = build_cfg(body)
    out = live_out(cfg)
    first = cfg.owner_blocks()[body[0]]
    assert "t" in out[first]
