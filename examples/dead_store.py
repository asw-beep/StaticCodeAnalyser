def pick(flag):
    label = compute_default()  # dead-store: every branch overwrites it
    if flag:
        label = "on"
    else:
        label = "off"
    return label


def retry_count(config):
    count = config.get("retries")  # dead-store: overwritten before any read
    count = 3
    return count


def fine(flag):
    result = None  # default-value initialization: not reported
    if flag:
        result = 1
    else:
        result = 2
    return result
