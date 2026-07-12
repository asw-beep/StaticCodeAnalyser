"""Triggers all six rules in one file — used as a multi-rule integration fixture."""


def buggy(x):
    unused = 99               # unused-variable
    z = 0
    result = x / z            # division-by-zero (ERROR, name tracked)
    return result
    print("never runs")       # dead-code


def maybe(x, divisor):
    return x / divisor        # division-by-zero (INFO)


def run_untrusted(expr):
    return eval(expr)         # unsafe-execution (ERROR)


API_KEY = "sk-live-abc123def456"  # hardcoded-secrets (ERROR)


def query_user(cursor, user_id):
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")  # sql-injection (ERROR)
    return API_KEY
