from django.db import DEFAULT_DB_ALIAS, connections
from django.test.utils import CaptureQueriesContext


class _AssertNumQueriesContext(CaptureQueriesContext):
    # Inspired by /django/test/testcases.py
    # but copied over to work without the unit test module
    def __init__(self, num, connection):
        self.num = num
        super(_AssertNumQueriesContext, self).__init__(connection)

    def __exit__(self, exc_type, exc_value, traceback):
        super(_AssertNumQueriesContext, self).__exit__(exc_type, exc_value, traceback)
        if exc_type is not None:
            return
        executed = len(self)
        assert executed == self.num, "%d queries executed, %d expected\nCaptured queries were:\n%s" % (
            executed, self.num,
            '\n'.join(
                query['sql'] for query in self.captured_queries
            )
        )


def assert_num_queries(num, func=None, *args, **kwargs):
    using = kwargs.pop("using", DEFAULT_DB_ALIAS)
    conn = connections[using]

    context = _AssertNumQueriesContext(num, conn)
    if func is None:
        return context

    with context:
        func(*args, **kwargs)
