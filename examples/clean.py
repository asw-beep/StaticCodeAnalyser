"""A file with no analyzer findings — used as a negative-control fixture."""


def add(a, b):
    total = a + b
    return total


def greet(name):
    print("hello", name)


for i in range(3):
    print(i)
