import ast

from analyzer.rules.sql_injection import SqlInjectionRule


def _check(src: str):
    return SqlInjectionRule().check(ast.parse(src))


def test_fstring_query_is_error():
    f = _check('cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")\n')
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_string_concat_query_is_error():
    f = _check('cursor.execute("SELECT * FROM users WHERE id = " + user_id)\n')
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_percent_formatting_query_is_error():
    f = _check('cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)\n')
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_str_format_query_is_error():
    f = _check('cursor.execute("SELECT * FROM users WHERE id = {}".format(user_id))\n')
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_executemany_dynamic_sql_is_error():
    f = _check('cursor.executemany(f"INSERT INTO t VALUES ({v})", rows)\n')
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_parameterized_query_is_safe():
    f = _check('cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))\n')
    assert f == []


def test_plain_string_query_no_params_is_safe():
    f = _check('cursor.execute("SELECT * FROM users")\n')
    assert f == []


def test_nested_attribute_receiver_is_checked():
    f = _check('self.db.cursor.execute(f"DELETE FROM t WHERE id = {tid}")\n')
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_unrelated_call_is_not_flagged():
    f = _check('logger.info(f"user id = {user_id}")\n')
    assert f == []


def test_no_execute_calls_no_findings():
    f = _check("def f(a, b):\n    return a + b\n")
    assert f == []


# --- traced through variables (dataflow) --------------------------------------


def _lines(src: str) -> list[int]:
    return [f.line for f in _check(src)]


def test_query_built_earlier_with_concat_is_error():
    f = _check("def f(c, uid):\n    q = 'SELECT * FROM u WHERE id = ' + uid\n    c.execute(q)\n")
    assert len(f) == 1 and f[0].line == 3
    assert "string concatenation (line 2)" in f[0].message


def test_query_extended_with_augmented_concat_is_error():
    src = "def f(c, uid):\n    q = 'SELECT * FROM u WHERE id = '\n    q += uid\n    c.execute(q)\n"
    assert _lines(src) == [4]


def test_query_dynamic_on_one_branch_is_error():
    src = "def f(c, uid, x):\n    q = 'SELECT 1'\n    if x:\n        q = 'SELECT ' + uid\n    c.execute(q)\n"
    assert _lines(src) == [5]


def test_query_built_in_loop_is_error():
    src = (
        "def f(c, ids):\n    q = 'SELECT * FROM t WHERE id IN ('\n"
        "    for i in ids:\n        q += str(i) + ','\n    c.execute(q)\n"
    )
    assert _lines(src) == [5]


def test_parameterized_query_built_from_literals_is_safe():
    src = (
        "def f(c, a, b):\n    q = 'SELECT * FROM u WHERE a = ?'\n"
        "    q += ' AND b = ?'\n    c.execute(q, (a, b))\n"
    )
    assert _lines(src) == []


def test_query_from_static_variables_is_safe():
    src = "def f(c):\n    base = 'SELECT * FROM u'\n    q = base + ' WHERE a = ?'\n    c.execute(q, (1,))\n"
    assert _lines(src) == []


def test_reassigned_to_literal_is_safe():
    assert _lines("def f(c, uid):\n    q = 'SELECT ' + uid\n    q = 'SELECT 1'\n    c.execute(q)\n") == []


def test_numeric_addition_is_not_string_building():
    assert _lines("def f(c, a, b):\n    n = a + b\n    c.execute(n)\n") == []
