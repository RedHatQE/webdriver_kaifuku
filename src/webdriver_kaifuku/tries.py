"""copied from cfme.utils"""


class TriesExceeded(Exception):
    """Default exception raised when tries() method doesn't catch a func exception"""

    pass


def tries(num_tries, exceptions, f, *args, **kwargs):
    """Tries to call the function multiple times if specific exceptions occur.

    Args:
        num_tries: How many times to try if exception is raised
        exceptions: exceptions that should be treated as repeat.
        f: Callable to be called.
        *args: Arguments to be passed through to the callable
        **kwargs: Keyword arguments to be passed through to the callable

    Returns:
        What ``f`` returns.

    Raises:
        What ``f`` raises if the try count is exceeded.
    """
    caught_exception = TriesExceeded(
        "Tries were exhausted without a specific function exception"
    )
    used_tries = 0
    while used_tries < num_tries:
        used_tries += 1
        try:
            return f(*args, **kwargs)
        except exceptions as e:
            caught_exception = e
    else:
        raise caught_exception
