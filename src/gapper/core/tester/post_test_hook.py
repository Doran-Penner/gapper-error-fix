"""The post test hook."""
from __future__ import annotations

from gapper.core.test_result import TestResult
from gapper.core.tester.hook import HookBase, HookTypes
from gapper.gradescope.datatypes.gradescope_meta import (
    GradescopeSubmissionMetadata,
)


class PostTests(HookBase):
    """A decorator for post tests. Will be used as @post_tests() decorator."""

    _hook_type = HookTypes.POST_TESTS

    def __repr__(self) -> str:
        """Return the representation of the post-test."""
        return (
            f"PostTest(post_test_fn={self.hook_fn}, as_test_case={self.as_test_case})"
        )

    def _run(
        self,
        *args,
        result_proxy: TestResult,
        metadata: GradescopeSubmissionMetadata | None,
    ) -> None:
        self.hook_fn_res = self.hook_fn(*args, result_proxy, metadata)
        self.process_generator()


post_tests = PostTests
