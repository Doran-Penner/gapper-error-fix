from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Iterable


if TYPE_CHECKING:
    from gap.core.errors import ErrorFormatter
    from gap.gradescope.datatypes.gradescope_output import PassStateType


@dataclass
class TestResult:
    default_name: str
    name: str | None = None
    score: float | None = field(default=None)
    max_score: float | None = field(default=None)
    weight: int | None = field(default=None)
    extra_score: float | None = field(default=None)
    errors: List[ErrorFormatter] = field(default_factory=list)
    pass_status: PassStateType = "passed"
    hidden: bool = False
    descriptions: List[str] = field(default_factory=list)

    def has_valid_score(self) -> None:
        assert (
            self.score is None or self.score >= 0
        ), f"Score must be non-negative ({self.rich_test_name})."
        assert (
            self.max_score is None or self.max_score >= 0
        ), f"Max score must be non-negative ({self.rich_test_name})."
        assert (
            self.weight is None or self.weight >= 0
        ), f"Weight must be non-negative ({self.rich_test_name}."
        assert (
            self.extra_score is None or self.extra_score >= 0
        ), f"Extra score must be non-negative ({self.rich_test_name})."

    @property
    def rich_test_name(self) -> str:
        name = f"{self.name} " if self.name else ""
        default_name = self.default_name
        return "{}{}".format(name, default_name)

    @property
    def rich_test_output(self) -> str:
        descriptions = "Description(s): " + "\n".join(self.descriptions)
        error_msg = "Error(s): \n" + (
            "\n".join(err.format() for err in self.errors) if self.errors else ""
        )

        return f"{descriptions}\n" f"{error_msg}"

    def set_name(self, name: str) -> None:
        self.name = name

    def add_description(self, detail: str) -> None:
        self.descriptions.append(detail)

    def set_description(self, detail: Iterable[str]) -> None:
        self.descriptions = list(detail)

    def set_hidden(self, hidden: bool) -> None:
        self.hidden = hidden

    def set_score(self, score: float) -> None:
        self.score = score

    def set_extra_score(self, score: float) -> None:
        self.extra_score = score

    def add_error(self, error: ErrorFormatter, set_failed: bool = True) -> None:
        self.errors.append(error)
        if set_failed:
            self.set_status("failed")

    def set_status(self, status: PassStateType) -> None:
        self.pass_status = status