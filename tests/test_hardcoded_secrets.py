import ast

from analyzer.rules.hardcoded_secrets import HardcodedSecretsRule


def _check(src: str):
    return HardcodedSecretsRule().check(ast.parse(src))


def test_hardcoded_password_assignment_is_error():
    f = _check("password = 'hunter2'\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_hardcoded_api_key_variants():
    f = _check("api_key = 'sk-live-abc123'\napikey = 'sk-live-def456'\n")
    assert len(f) == 2


def test_hardcoded_secret_ann_assign_is_error():
    f = _check("SECRET_TOKEN: str = 'abc123def456'\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_hardcoded_password_keyword_arg_is_error():
    f = _check("connect(host='db', password='hunter2')\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_hardcoded_token_keyword_arg_is_error():
    f = _check("Client(api_key='sk-live-abc123')\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_empty_string_is_not_flagged():
    f = _check("password = ''\n")
    assert f == []


def test_changeme_placeholder_is_not_flagged():
    f = _check("password = 'changeme'\n")
    assert f == []


def test_xxx_placeholder_is_not_flagged():
    f = _check("api_key = 'xxx'\n")
    assert f == []


def test_all_asterisk_placeholder_is_not_flagged():
    f = _check("secret = '****'\n")
    assert f == []


def test_non_string_value_is_not_flagged():
    f = _check("password = get_password()\n")
    assert f == []


def test_non_credential_name_is_not_flagged():
    f = _check("greeting = 'hello world'\n")
    assert f == []


def test_no_secrets_no_findings():
    f = _check("def f(a, b):\n    return a + b\n")
    assert f == []
