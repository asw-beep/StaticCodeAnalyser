import os
import shlex
import sys

from flask import Flask, request, send_file

app = Flask(__name__)


@app.route("/ping")
def ping():
    host = request.args["host"]          # source
    cmd = "ping -c 1 " + host            # taint propagates through concatenation
    os.system(cmd)                       # tainted-data: command injection


@app.route("/ping-safe")
def ping_safe():
    host = shlex.quote(request.args["host"])  # sanitized
    os.system("ping -c 1 " + host)            # no tainted-data (unsafe-execution still flags the API)


@app.route("/download/<name>")
def download(name):                      # route parameters are sources
    return send_file("/srv/files/" + name)  # tainted-data: path traversal


@app.route("/user/<int:uid>")
def user(uid: int):                      # typed parameter: already parsed, safe
    return send_file(f"/srv/avatars/{uid}.png")


def main():
    for arg in sys.argv[1:]:
        print(eval(arg))                 # tainted-data: code injection
