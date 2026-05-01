def f(x):
    return x + 1
    print("unreachable")


def g():
    for i in range(3):
        break
        print("also unreachable")
