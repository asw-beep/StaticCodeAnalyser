import ast

import pytest

from analyzer.rules.tainted_data import TaintedDataRule


def _check(src: str):
    return TaintedDataRule().check(ast.parse(src))


def _hits(src: str) -> list[tuple[int, str]]:
    """(line, vulnerability class) per finding."""
    return [(f.line, f.message.rsplit("possible ", 1)[1]) for f in _check(src)]


def test_message_names_source_line_and_sink():
    src = "def ping():\n    host = request.args['host']\n    cmd = 'ping -c 1 ' + host\n    os.system(cmd)\n"
    [f] = _check(src)
    assert f.severity == "ERROR" and f.line == 4
    assert f.message == (
        "Untrusted input from request.args (line 2) reaches 'os.system()': possible command injection"
    )


@pytest.mark.parametrize(
    "src, expected",
    [
        ("def f():\n    cur.execute(request.form['q'])\n", [(2, "SQL injection")]),
        ("import sys, subprocess\nsubprocess.run(sys.argv[1], shell=True)\n", [(2, "command injection")]),
        ("def f():\n    eval(input())\n", [(2, "code injection")]),
        ("def f():\n    return open('/srv/' + request.args['p']).read()\n", [(2, "path traversal")]),
        (
            "def f():\n    return requests.get(request.json.get('url'))\n",
            [(2, "server-side request forgery")],
        ),
        ("def f():\n    return pickle.loads(request.data)\n", [(2, "unsafe deserialization")]),
    ],
)
def test_each_sink_class(src, expected):
    assert _hits(src) == expected


@pytest.mark.parametrize(
    "src, line",
    [
        # through a loop variable
        ("def f():\n    for line in sys.stdin:\n        os.system(line)\n", 3),
        # through a container mutated with append()
        ("def f():\n    parts = []\n    parts.append(input())\n    os.system(' '.join(parts))\n", 4),
        # through a with-target
        ("def f():\n    with stream(request.args['p']) as fh:\n        pickle.load(fh)\n", 3),
        # through walrus
        ("def f():\n    if (x := input()):\n        eval(x)\n", 3),
        # tainted on one branch only (may-analysis)
        ("def f(c):\n    x = 'safe'\n    if c:\n        x = input()\n    eval(x)\n", 5),
        # Django class-based view
        ("class V:\n    def get(self):\n        q = self.request.GET['q']\n        cursor.execute(q)\n", 4),
        # module-level script
        ("import sys, os\nos.system('rm ' + sys.argv[1])\n", 2),
    ],
)
def test_taint_propagates(src, line):
    assert [f.line for f in _check(src)] == [line]


def test_route_handler_parameters_are_sources():
    src = "@app.route('/f/<name>')\ndef f(name):\n    return open('/data/' + name).read()\n"
    [f] = _check(src)
    assert "route parameter 'name' (line 2)" in f.message


@pytest.mark.parametrize(
    "src",
    [
        # sanitizers
        "def f():\n    os.system('ping ' + shlex.quote(request.args['h']))\n",
        "def f():\n    eval(int(input()))\n",
        "def f():\n    return open('/srv/' + os.path.basename(request.args['p']))\n",
        # comparisons produce clean booleans
        "def f():\n    ok = input() == 'yes'\n    eval(ok)\n",
        # reassignment clears taint
        "def f():\n    x = input()\n    x = 'safe'\n    eval(x)\n",
        # parameterized SQL: the tainted value is a bound parameter, not the query
        "def f():\n    cur.execute('SELECT * FROM t WHERE id = ?', (request.args['id'],))\n",
        # list-form subprocess without a shell
        "import sys, subprocess\nsubprocess.run(['ls', sys.argv[1]])\n",
        # typed route parameter already parsed by the framework
        "@app.get('/u/{uid}')\ndef f(uid: int):\n    cur.execute('SELECT ' + str(uid))\n",
        # ordinary function parameters are not sources (intra-procedural)
        "def f(name):\n    return open(name).read()\n",
    ],
)
def test_not_tainted(src):
    assert _check(src) == []
