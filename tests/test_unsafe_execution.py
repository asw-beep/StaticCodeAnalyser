import ast

from analyzer.rules.unsafe_execution import UnsafeExecutionRule


def _check(src: str):
    return UnsafeExecutionRule().check(ast.parse(src))


def test_eval_is_error():
    f = _check("eval('1+1')\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_exec_is_error():
    f = _check("exec('print(1)')\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_compile_is_error():
    f = _check("compile('1+1', '<string>', 'eval')\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_eval_of_input_is_still_error():
    f = _check("eval(input())\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_os_system_is_error():
    f = _check("import os\nos.system('rm -rf /')\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_subprocess_shell_true_is_error():
    f = _check("import subprocess\nsubprocess.run(cmd, shell=True)\n")
    assert len(f) == 1 and f[0].severity == "ERROR"


def test_subprocess_without_shell_is_safe():
    f = _check("import subprocess\nsubprocess.run(['ls'])\n")
    assert f == []


def test_subprocess_shell_false_is_safe():
    f = _check("import subprocess\nsubprocess.run(cmd, shell=False)\n")
    assert f == []


def test_pickle_load_is_warning():
    f = _check("import pickle\npickle.load(fh)\n")
    assert len(f) == 1 and f[0].severity == "WARNING"


def test_pickle_loads_is_warning():
    f = _check("import pickle\npickle.loads(data)\n")
    assert len(f) == 1 and f[0].severity == "WARNING"


def test_yaml_load_without_safe_loader_is_warning():
    f = _check("import yaml\nyaml.load(data)\n")
    assert len(f) == 1 and f[0].severity == "WARNING"


def test_yaml_load_with_safe_loader_is_safe():
    f = _check("import yaml\nyaml.load(data, Loader=yaml.SafeLoader)\n")
    assert f == []


def test_yaml_safe_load_is_safe():
    f = _check("import yaml\nyaml.safe_load(data)\n")
    assert f == []


def test_no_unsafe_calls_no_findings():
    f = _check("def f(a, b):\n    return a + b\n")
    assert f == []
