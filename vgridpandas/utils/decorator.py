from functools import wraps
from typing import Callable, Iterator


def catch_invalid_dggs_id(f: Callable) -> Callable:
    """Wrapper that catches potential invalid  DGGS ID."""

    @wraps(f)
    def safe_f(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except (TypeError, ValueError) as e:
            message = "DGGS method raised an error. Is the DGGS ID correct?"
            message += f"\nCaller: {f.__name__}({_print_signature(*args, **kwargs)})"
            message += f"\nOriginal error: {repr(e)}"
            raise ValueError(message)

    return safe_f


def sequential_deduplication(func: Iterator[str]) -> Iterator[str]:
    """Decorator that doesn't permit two consecutive items of an iterator to be the same."""

    def inner(*args):
        iterable = func(*args)
        last = None
        while (cell := next(iterable, None)) is not None:
            if cell != last:
                yield cell
            last = cell

    return inner


def doc_standard(column_name: str, description: str) -> Callable:
    """Wrapper to provide a standard apply-to-DGGS-id docstring."""

    def doc_decorator(f):
        @wraps(f)
        def doc_f(*args, **kwargs):
            return f(*args, **kwargs)

        parameters = f.__doc__ or ""
        doc = f"""Adds the column `{column_name}` {description}. Assumes DGGS ID.
        {parameters}
        Returns
        -------
        Geo(DataFrame) with `{column_name}` column added

        Raises
        ------
        ValueError
            When an invalid DGGS address is encountered
        """
        doc_f.__doc__ = doc
        return doc_f

    return doc_decorator


def _print_signature(*args, **kwargs):
    signature = []
    if args:
        signature.append(", ".join([repr(a) for a in args]))
    if kwargs:
        signature.append(", ".join({f"{repr(k)}={repr(v)}" for k, v in kwargs.items()}))
    return ", ".join(signature)
