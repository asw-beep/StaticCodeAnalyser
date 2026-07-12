def get_user_fstring(cursor, user_id):
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")  # sql-injection (ERROR)


def get_user_concat(cursor, user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)  # not flagged: query built earlier, not at the call site


def get_user_inline_concat(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = " + user_id)  # sql-injection (ERROR)


def get_user_percent(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)  # sql-injection (ERROR)


def get_user_format(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = {}".format(user_id))  # sql-injection (ERROR)


def get_user_safe(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))  # safe, parameterized
