from __future__ import annotations

from collections.abc import Callable
from typing import Any, NoReturn

from .errors import ByteparseError, DefinitionError, ParseError


class Context:
    """Fields of the struct being parsed, plus the enclosing context as _parent."""

    __slots__ = ("_values", "_parent")

    def __init__(self, values: dict[str, Any], parent: Context | None) -> None:
        self._values = values
        self._parent = parent

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(f"field {name!r} has not been parsed") from None


def _no_operators(self: Ref, *args: object) -> NoReturn:
    raise DefinitionError(
        f"{self!r} does not support operators; use a lambda, e.g. lambda ctx: ..."
    )


class Ref:
    __slots__ = ("_path",)

    def __init__(self, path: tuple[str, ...]) -> None:
        self._path = path

    def __getattr__(self, name: str) -> Ref:
        if name.startswith("__"):
            raise AttributeError(name)
        return Ref((*self._path, name))

    def __repr__(self) -> str:
        return "this" + "".join(f".{p}" for p in self._path)

    __eq__ = __ne__ = __lt__ = __le__ = __gt__ = __ge__ = _no_operators
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _no_operators
    __floordiv__ = __truediv__ = __mod__ = __and__ = __or__ = __xor__ = _no_operators
    __lshift__ = __rshift__ = __neg__ = __invert__ = __bool__ = _no_operators
    __hash__ = None  # type: ignore[assignment]

    def resolve(self, ctx: Context) -> Any:
        value: Any = ctx
        for part in self._path:
            try:
                value = getattr(value, part)
            except AttributeError:
                raise ParseError(f"{self!r} is not available") from None
        return value


this: Any = Ref(())

Expr = Any  # int constant, Ref, or Callable[[Context], Any]


def is_expr(value: object) -> bool:
    return isinstance(value, Ref) or callable(value)


def call_user(fn: Callable[..., Any], *args: Any, what: str) -> Any:
    try:
        return fn(*args)
    except ByteparseError:
        raise
    except Exception as e:
        raise ParseError(f"{what} raised {type(e).__name__}: {e}") from e


def resolve(expr: Expr, ctx: Context, what: str) -> Any:
    if isinstance(expr, Ref):
        return expr.resolve(ctx)
    if callable(expr):
        return call_user(expr, ctx, what=what)
    return expr


def resolve_size(expr: Expr, ctx: Context, what: str = "size") -> int:
    value = resolve(expr, ctx, what)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ParseError(f"{what} must be a non-negative int, got {value!r}")
    return value


def check_size_arg(value: object, what: str) -> None:
    if is_expr(value):
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DefinitionError(
            f"{what} must be a non-negative int, this reference or lambda, got {value!r}"
        )
