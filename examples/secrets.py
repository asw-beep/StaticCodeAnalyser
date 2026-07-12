API_KEY = "sk-live-abc123def456"  # hardcoded-secrets (ERROR)


def connect():
    password = "hunter2"  # hardcoded-secrets (ERROR)
    return Database(host="db.internal", password=password)


def connect_inline():
    return Database(host="db.internal", password="hunter2")  # hardcoded-secrets (ERROR)


def connect_safely():
    import os

    token = os.environ["API_TOKEN"]  # safe, no finding
    placeholder_password = "changeme"  # safe, placeholder
    return token, placeholder_password
