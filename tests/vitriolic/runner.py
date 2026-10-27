"""Test runner that lets the parallel workers report a failing ``subTest``.

A failed ``subTest`` is sent from the worker to the parent as a ``_SubTest``
that holds the whole ``TestCase``. ``SimpleTestCase.__getstate__`` drops the
unpicklable attributes, but only while ``_outcome`` is set, that is while the
test runs. Django checks the subtest then, and it passes. The worker sends its
events after the test has finished, ``_outcome`` is ``None`` by then, and the
full state is pickled, including django-test-plus's ``last_response`` with
its ``ResolverMatch``. The run ends with ``MaybeEncodingError`` and the
assertion is lost.

``SubTestSnapshotResult`` records a pickled copy of the subtest at the moment
it fails, while the state is still filtered, so the parent gets the failure.
"""

import pickle

from django.test.runner import (
    DiscoverRunner,
    ParallelTestSuite,
    RemoteTestResult,
    RemoteTestRunner,
)


class SubTestSnapshotResult(RemoteTestResult):
    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            name, test_index, _, err = self.events[-1]
            snapshot = pickle.loads(pickle.dumps(subtest))
            self.events[-1] = (name, test_index, snapshot, err)


class SubTestSnapshotRunner(RemoteTestRunner):
    resultclass = SubTestSnapshotResult


class SubTestSnapshotSuite(ParallelTestSuite):
    runner_class = SubTestSnapshotRunner


class TestRunner(DiscoverRunner):
    parallel_test_suite = SubTestSnapshotSuite
