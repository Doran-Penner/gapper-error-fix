from typing import Any, Type

from gap import problem, test_case
from gap.core.test_result import TestResult
from gap.core.unittest_wrapper import TestCaseWrapper


class GasStation:
    pass


def test_override(
    tc: TestCaseWrapper, result: TestResult, solution: Type, submission: Type
) -> None:
    gas_station = tc.context.GasStation()
    sol_obj = solution(gas_station)
    sub_obj = submission(gas_station)
    tc.assertEqual(sol_obj.gas_station, sub_obj.gas_station)

    result.set_status("passed")


@test_case(gap_override_test=test_override)
@problem(context=("GasStation",))
class Car:
    def __init__(self, gas_station: GasStation):
        self.gas_station = gas_station


__problem_config__ = {
    "is_script": False,
    "check_stdout": False,
    "mock_input": False,
    "captured_context": ("GasStation",),
}