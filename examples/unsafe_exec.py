import os
import pickle
import subprocess

import yaml


def run_user_code(expr):
    return eval(expr)  # unsafe-execution (ERROR)


def run_shell(cmd):
    os.system(cmd)  # unsafe-execution (ERROR)
    subprocess.run(cmd, shell=True)  # unsafe-execution (ERROR)


def load_data(fh, raw):
    pickle.load(fh)  # unsafe-execution (WARNING)
    yaml.load(raw)  # unsafe-execution (WARNING)


def load_data_safely(raw):
    return yaml.safe_load(raw)  # safe, no finding
