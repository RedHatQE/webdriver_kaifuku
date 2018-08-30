"""copied from cfme.utils"""


def tries(num_tries, exceptions, f, *args, **kwargs):
    """ Tries to call the function multiple times if specific exceptions occur.

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
    tries = 0
    failure = None
    while tries < num_tries:
        tries += 1
        try:
            return f(*args, **kwargs)
        except exceptions as e:
            failure = e
    else:
        assert failure is not None
        raise failure
