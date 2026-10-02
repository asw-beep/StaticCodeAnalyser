# Stage 8 — Forward dataflow and taint tracking

**Status:** complete
**Code:** `analyzer/dataflow.py`, `analyzer/rules/sql_injection.py`, `analyzer/rules/tainted_data.py`

## Why

Pattern rules only see the call site. Both of these slipped through:

```python
query = "SELECT * FROM users WHERE id = " + user_id
cursor.execute(query)            # the dangerous shape is one line up

host = request.args["host"]
os.system("ping " + host)        # is `host` attacker-controlled? the call can't say
```

Answering either needs to know where a variable's value came from at the point it's used. That is a forward dataflow problem, solved on the CFG from stage 7.

## The engine (`analyzer/dataflow.py`)

The engine is a forward may-analysis. For every program point it computes an *environment* that maps each variable to an `Origin` (line and description) when its value carries the property being tracked.

```
in(B)  = ∪ out(P)  over predecessors P      (merge: earliest origin wins, so output is deterministic)
out(B) = transfer(in(B), items of B)
```

It runs as a worklist to a fixed point. The tracked property is a plug-in: each rule supplies an `evaluate(expr, env) -> Origin | None` function, and the transfer rules are shared:

| Statement | Effect |
|---|---|
| `x = e` | **Strong update.** `x` gets `evaluate(e)`, or *loses* the property. This is what makes `x = input(); x = "safe"` clean. |
| `a, b = e` | Every unpacked name gets `evaluate(e)`. |
| `x += e` | `x` keeps what it had and gains `evaluate(x + e)`. |
| `x[k] = e`, `x.a = e`, `x.append(e)` | **Weak update** of `x`: it can gain the property but never loses it. Containers are tracked as a whole. |
| `for x in e`, `with e as x`, `case <capture>` | `x` takes the property of `e`. |
| `x := e` anywhere | Strong update. |
| `def x`, `class x`, `del x`, `except … as x` | Clear `x`. |

Merging uses union (a *may* analysis). A value tainted on *any* path into a point is treated as tainted there. For a security rule that's the right default: an attacker only needs one path.

## Rule 1: SQL queries traced through variables

The property is "this string was built dynamically". The evaluator marks f-strings with placeholders, and concatenation, `%`, `.format()` and `.join()` with a non-constant piece.

What counts as a "constant piece" decides whether the rule is noisy. Step-by-step parameterized queries are common and safe:

```python
q = "SELECT * FROM t WHERE a = ?"
q += " AND b = ?"
cursor.execute(q, (a, b))
```

So before running the flow analysis, the rule computes two flow-insensitive facts per scope, iterated to a fixed point:
- **Static names:** every binding of the name is a string literal or a static concatenation. A concatenation is dynamic only if some piece is neither a literal nor a static name.
- **Stringy names:** at least one binding of the name is string-shaped. This separates `q += uid` (string building) from `n = a + b` (arithmetic).

The original inline check keeps its exact messages. A traced finding adds the line where the query was built: `SQL query built with string concatenation (line 6) instead of a parameterized query in 'execute()'`.

## Rule 2: `tainted-data`

The property is "derived from untrusted input".

- **Sources** are `input()`, `sys.argv`, `sys.stdin`, `request.<args|form|json|…>` (also `self.request.…` for Django class-based views), and route-handler parameters. Route handlers are recognised by decorators like `@app.route`, `@router.get` and `@app.post`. Parameters annotated `int`, `float`, `bool` or `UUID` are exempt, because the framework has already parsed them.
- **Propagation is the default.** A call, attribute, subscript, operator or container is tainted if any input to it is. That includes a method's receiver: `x.strip()` and `x.get("k")` stay tainted.
- **Sanitizers** return clean values: `int()`, `shlex.quote()`, `html.escape()`, `os.path.basename()`, `secure_filename()`, and others. Comparisons also produce clean booleans.
- **Sinks** are grouped by vulnerability class, and the message names the class:
  - SQL injection
  - command injection (`os.system`, or `subprocess` with `shell=True` only; the list form is the safe pattern)
  - code injection
  - path traversal
  - SSRF
  - unsafe deserialization

The message gives the source, its line, the sink and the class, for example: `Untrusted input from request.args (line 12) reaches 'os.system()': possible command injection`.

### Overlap with other rules

`unsafe-execution` and `sql-injection` flag *dangerous shapes* whatever the data. `tainted-data` flags *demonstrated flows* of untrusted data. They can fire on the same line on purpose, because they answer different questions. "This API is risky" is a code-review finding. "Attacker input reaches it from line 12" is a vulnerability. Use `--ignore` or `[tool.analyzer] ignore` to keep one of them.

## Validation

- Unit tests cover every sink class, each propagation path (loop variable, container mutation, `with`-target, walrus, one-branch-only taint, Django CBV, module-level script) and each way of staying clean (sanitizers, comparisons, reassignment, parameterized SQL, list-form `subprocess`, typed route parameters).
- Running the analyzer on its own source still produces no findings at WARNING or above.

## Limitations

- **Intra-procedural:** taint returned from a helper, or passed into one, is not followed (except via route-handler parameters). Inter-procedural summaries are the natural next step.
- **Sanitizers are not class-specific:** `shlex.quote()` clears taint for every sink, not only for shell commands.
- **Names aren't resolved through imports:** `from os import system as run; run(x)` is missed.
- **Containers are tracked as a whole,** not per element or per key.
