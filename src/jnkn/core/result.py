"""
Result Type Implementation.

This module provides a Rust-like Result type (Ok/Err) to enforce explicit
error handling. This facilitates the future migration to Rust by eliminating
implicit exception control flows in core logic.
"""

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """
    Represents a successful computation.
    Maps to Rust's Result::Ok.
    """
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value


@dataclass(frozen=True)
class Err(Generic[E]):
    """
    Represents a failed computation.
    Maps to Rust's Result::Err.
    """
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> T:
        raise ValueError(f"Called unwrap on Err: {self.error}")


# Type alias for the Result
Result = Union[Ok[T], Err[E]]


def map_ok(result: Result[T, E], func: Callable[[T], U]) -> Result[U, E]:
    """
    Apply a function to the contained value if Ok, otherwise return Err.
    Maps to Rust's Result::map.
    """
    if isinstance(result, Ok):
        return Ok(func(result.value))
    return result  # type: ignore
