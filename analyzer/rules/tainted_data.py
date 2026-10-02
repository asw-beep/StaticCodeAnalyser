"""Tainted-data rule: untrusted input reaching a dangerous call.

Classic source -> sink taint tracking, run per scope with the forward
dataflow engine (`analyzer/dataflow.py`):

    name = request.args["name"]          # source
    cmd = "ping -c 1 " + name            # taint propagates
    os.system(cmd)                       # sink -> ERROR, cites line 1

Sources (untrusted input):
- `input()`, `sys.argv`, `sys.stdin`
- web request data: `request.args/form/values/json/data/files/cookies/
  headers/GET/POST/body/query_params/...` (Flask, Django, Starlette), also
  as `self.request.<attr>`
- parameters of route handlers (functions decorated with `@x.route(...)`,
  `@x.get(...)`, `@x.post(...)`, ...), except ones annotated `int`,
  `float`, `bool` or `uuid.UUID`, which the framework has already parsed

Sanitizers (their result is clean): `int`, `float`, `bool`, `len`, `abs`,
`round`, `ord`, `isinstance`, `shlex.quote`, `html.escape`,
`markupsafe.escape`, `os.path.basename`, `secure_filename`,
`urllib.parse.quote`, `uuid.UUID`, `ipaddress.ip_address`. Comparisons
(`x == "admin"`) produce clean booleans.

Sinks, by vulnerability class:
- SQL injection:          `.execute()` / `.executemany()` / `.executescript()` query
- command injection:      `os.system`, `os.popen`, `subprocess.getoutput`,
                          `subprocess.*(..., shell=True)`
- code injection:         `eval`, `exec`
- path traversal:         `open`, `os.remove/unlink/rmdir`, `shutil.rmtree/copy/move`, `send_file`
- SSRF:                   `requests.*`, `httpx.*`, `urlopen` URL argument
- unsafe deserialization: `pickle.load(s)`, `marshal.loads`, `yaml.load`

Everything else propagates taint: a call, attribute, subscript, operator or
container is tainted if any input to it is.

Overlap with other rules is intentional: `unsafe-execution` flags `eval()`
because the API is dangerous; this rule flags it because untrusted data
demonstrably reaches it, and says from where.

Limitations (deliberate):
- Intra-procedural: taint through a helper function's return value or
  into its parameters is not followed (except route-handler parameters).
- A sanitizer clears taint for every sink class (`shlex.quote()` output
  reaching `eval()` is not reported).
- Calls are matched by dotted name, without resolving imports or aliases.
"""

from __future__ import annotations

import ast

from analyzer.dataflow import Env, Origin, analyze_flow, walk_scope
from analyzer.reporter import Finding
from analyzer.rules.base import Rule

_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)

_REQUEST_ATTRS = {
    "args", "form", "values", "json", "data", "files", "cookies", "headers",
    "get_json", "get_data", "GET", "POST", "body", "query_params", "path_params",
}  # fmt: skip
_SOURCE_ATTRS = {"sys.argv", "sys.stdin"}
_SOURCE_CALLS = {"input"}

_SANITIZERS = {
    "int", "float", "bool", "len", "abs", "round", "ord", "isinstance",
    "shlex.quote", "html.escape", "escape", "markupsafe.escape", "os.path.basename",
    "secure_filename", "werkzeug.utils.secure_filename", "urllib.parse.quote",
    "quote", "uuid.UUID", "UUID", "ipaddress.ip_address",
}  # fmt: skip

_ROUTE_DECORATORS = {"route", "get", "post", "put", "patch", "delete", "api_route", "websocket"}
_SAFE_ANNOTATIONS = {"int", "float", "bool", "UUID", "uuid.UUID"}

_HTTP_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "request"}

# dotted call name -> (vulnerability class, positional index, keyword name)
_SINKS: dict[str, tuple[str, int, str]] = {
    "os.system": ("command injection", 0, "command"),
    "os.popen": ("command injection", 0, "cmd"),
    "subprocess.getoutput": ("command injection", 0, "cmd"),
    "subprocess.getstatusoutput": ("command injection", 0, "cmd"),
    "eval": ("code injection", 0, "source"),
    "exec": ("code injection", 0, "source"),
    "open": ("path traversal", 0, "file"),
    "io.open": ("path traversal", 0, "file"),
    "os.remove": ("path traversal", 0, "path"),
    "os.unlink": ("path traversal", 0, "path"),
    "os.rmdir": ("path traversal", 0, "path"),
    "shutil.rmtree": ("path traversal", 0, "path"),
    "shutil.copy": ("path traversal", 0, "src"),
    "shutil.copyfile": ("path traversal", 0, "src"),
    "shutil.move": ("path traversal", 0, "src"),
    "send_file": ("path traversal", 0, "path_or_file"),
    "flask.send_file": ("path traversal", 0, "path_or_file"),
    "urlopen": ("server-side request forgery", 0, "url"),
    "urllib.request.urlopen": ("server-side request forgery", 0, "url"),
    "pickle.load": ("unsafe deserialization", 0, "file"),
    "pickle.loads": ("unsafe deserialization", 0, "data"),
    "marshal.loads": ("unsafe deserialization", 0, "bytes"),
    "yaml.load": ("unsafe deserialization", 0, "stream"),
    "yaml.unsafe_load": ("unsafe deserialization", 0, "stream"),
}
for _lib in ("requests", "httpx"):
    for _verb in _HTTP_VERBS:
        _SINKS[f"{_lib}.{_verb}"] = ("server-side request forgery", 1 if _verb == "request" else 0, "url")
_SQL_METHODS = {"execute", "executemany", "executescript"}
_SUBPROCESS_SHELL = {"call", "run", "Popen", "check_call", "check_output"}


def dotted_name(node: ast.expr) -> str | None:
    """'os.path.join' for an Attribute chain of Names, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _source(node: ast.expr) -> str | None:
    """Description of `node` if it reads untrusted input directly."""
    if isinstance(node, ast.Attribute):
        name = dotted_name(node)
        if name in _SOURCE_ATTRS:
            return name
        recv = node.value
        is_request = (isinstance(recv, ast.Name) and recv.id == "request") or (
            isinstance(recv, ast.Attribute) and recv.attr == "request"
        )
        if is_request and node.attr in _REQUEST_ATTRS:
            return f"request.{node.attr}"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SOURCE_CALLS:
        return f"{node.func.id}()"
    return None


def taint_of(node: ast.expr, env: Env) -> Origin | None:
    """Origin of untrusted data flowing into `node`'s value, if any."""
    if isinstance(node, ast.Name):
        return env.get(node.id)
    src = _source(node)
    if src:
        return Origin(node.lineno, src)
    if isinstance(node, (ast.Constant, ast.Compare, ast.Lambda)):
        return None
    if isinstance(node, ast.Call):
        name = dotted_name(node.func)
        if name in _SANITIZERS:
            return None
        inputs = [*node.args, *(k.value for k in node.keywords)]
        if isinstance(node.func, ast.Attribute):
            inputs.append(node.func.value)  # x.strip(), x.get("k"), ...
    else:
        inputs = [c for c in ast.iter_child_nodes(node) if isinstance(c, ast.expr)]
    found = [o for o in (taint_of(i, env) for i in inputs) if o is not None]
    return min(found) if found else None


def _sink(call: ast.Call) -> tuple[str, str, ast.expr] | None:
    """(display name, vulnerability class, argument) if `call` is a sink."""
    func = call.func
    name = dotted_name(func)

    def arg(pos: int, kw: str) -> ast.expr | None:
        if len(call.args) > pos:
            return call.args[pos]
        return next((k.value for k in call.keywords if k.arg == kw), None)

    if isinstance(func, ast.Attribute) and func.attr in _SQL_METHODS:
        a = arg(0, "sql")
        return (f"{func.attr}", "SQL injection", a) if a is not None else None
    if name and name.startswith("subprocess.") and name.split(".", 1)[1] in _SUBPROCESS_SHELL:
        shell = next((k.value for k in call.keywords if k.arg == "shell"), None)
        if isinstance(shell, ast.Constant) and shell.value is True:
            a = arg(0, "args")
            return (name, "command injection", a) if a is not None else None
        return None
    if name in _SINKS:
        cls, pos, kw = _SINKS[name]
        a = arg(pos, kw)
        return (name, cls, a) if a is not None else None
    return None


def _route_params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> Env:
    is_route = any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _ROUTE_DECORATORS
        for d in func.decorator_list
    )
    if not is_route:
        return {}
    env: Env = {}
    a = func.args
    for p in a.posonlyargs + a.args + a.kwonlyargs:
        if p.arg in {"self", "cls"}:
            continue
        if p.annotation is not None and dotted_name(p.annotation) in _SAFE_ANNOTATIONS:
            continue
        env[p.arg] = Origin(func.lineno, f"route parameter '{p.arg}'")
    return env


def _check_scope(body: list[ast.stmt], initial: Env) -> list[Finding]:
    flow = analyze_flow(body, taint_of, initial)
    findings: dict[tuple[int, str], Finding] = {}
    for item, env in flow.items_with_env():
        if item.kind in ("nop", "pattern") or isinstance(item.node, (*_FUNCS, ast.ClassDef)):
            continue
        for node in walk_scope(item.node):
            if not isinstance(node, ast.Call):
                continue
            sink = _sink(node)
            if sink is None:
                continue
            sink_name, cls, argument = sink
            origin = taint_of(argument, env)
            if origin is None:
                continue
            findings.setdefault(
                (node.lineno, sink_name),
                Finding(
                    severity="ERROR",
                    message=(
                        f"Untrusted input from {origin.desc} (line {origin.line}) "
                        f"reaches '{sink_name}()': possible {cls}"
                    ),
                    line=node.lineno,
                    rule="tainted-data",
                ),
            )
    return list(findings.values())


class TaintedDataRule(Rule):
    name = "tainted-data"
    description = "Untrusted input (request data, input(), argv) reaching SQL, shell, eval, file or URL sinks"

    def check(self, tree: ast.Module) -> list[Finding]:
        findings = _check_scope(tree.body, {})
        for node in ast.walk(tree):
            if isinstance(node, _FUNCS):
                findings.extend(_check_scope(node.body, _route_params(node)))
        return sorted(findings, key=lambda f: f.line)
