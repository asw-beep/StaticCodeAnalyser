"""Triggers all three rules in one file — used as a multi-rule integration fixture."""


def buggy(x):
    unused = 99               # unused-variable
    z = 0
    result = x / z            # division-by-zero (ERROR, name tracked)
    return result
    print("never runs")       # dead-code


def maybe(x, divisor):
    return x / divisor        # division-by-zero (INFO)
