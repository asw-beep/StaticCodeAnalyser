def f(x):
    return x + 1
    print("unreachable")


def g():
    for i in range(3):
        break
        print("also unreachable")


def sign(x):
    if x >= 0:
        return 1
    else:
        return -1
    print("unreachable: both branches return")


def serve():
    while True:
        handle_request()
    print("unreachable: infinite loop")
