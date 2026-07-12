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
