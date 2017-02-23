import contextlib

from django.conf import settings
from django.db import connection, transaction


class DummyRollbackException(Exception):
    pass


@contextlib.contextmanager
def rolledback_transaction():
    """
    This context manager runs your code in a database transaction that will be rolled back in the end.
    This can come in handy to simulate the effects of a database operation that you do not actually
    want to perform.

    Note that rollbacks are a very slow operation on most database backends. Also, long-running
    transactions can slow down other operations currently running and you should not use this
    in a place that is called frequently.
    """
    try:
        with transaction.atomic():
            yield
            raise DummyRollbackException()
    except DummyRollbackException:
        pass
    else:
        raise Exception('Invalid state, should have rolled back.')


if 'mysql' in settings.DATABASES['default']['ENGINE'] and settings.DATABASE_IS_GALERA:

    @contextlib.contextmanager
    def casual_reads():
        """
        When pretix runs with a MySQL galera cluster as a database backend, we can run into the
        following problem:

        * A celery thread starts a transaction, creates an object and commits the transaction.
          It then returns the object ID into celery's result store (e.g. redis)

        * A web thread pulls the object ID from the result store, but cannot access the object
          yet as the transaction is not yet committed everywhere.

        This sets the wsrep_sync_wait variable to deal with this problem.

        See also:

        * https://mariadb.com/kb/en/mariadb/galera-cluster-system-variables/#wsrep_sync_wait

        * https://www.percona.com/doc/percona-xtradb-cluster/5.6/wsrep-system-index.html#wsrep_sync_wait
        """
        with connection.cursor() as cursor:
            cursor.execute("SET @wsrep_sync_wait_orig = @@wsrep_sync_wait;")
            cursor.execute("SET SESSION wsrep_sync_wait = GREATEST(@wsrep_sync_wait_orig, 1);")
            try:
                yield
            finally:
                cursor.execute("SET SESSION wsrep_sync_wait = @wsrep_sync_wait_orig;")

else:

    @contextlib.contextmanager
    def casual_reads():
        yield
