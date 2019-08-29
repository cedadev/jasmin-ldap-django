"""
This module provides a Django database backend for LDAP.
"""

__author__ = "Matt Pryor"
__copyright__ = "Copyright 2015 UK Science and Technology Facilities Council"

import contextlib

from django.db.backends.base.client import BaseDatabaseClient
from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.backends.base.validation import BaseDatabaseValidation
from django.db.backends.base.introspection import BaseDatabaseIntrospection

from jasmin_ldap import ServerPool, Connection, AuthenticationError, Query as LDAPQuery


import logging
logger = logging.getLogger(__name__)


class DatabaseClient(BaseDatabaseClient):
    def runshell(self):
        raise NotImplementedError('Not currently supported')


class DatabaseCreation(BaseDatabaseCreation):
    def create_test_db(self, *args, **kwargs):
        raise NotImplementedError('Not currently supported')

    def destroy_test_db(self, *args, **kwargs):
        raise NotImplementedError('Not currently supported')


class DatabaseFeatures(BaseDatabaseFeatures):
    can_use_chunked_reads = False
    supports_select_related = False
    supports_subqueries_in_group_by = False
    supports_microsecond_precision = False
    supports_regex_backreferencing = False
    supports_timezones = False
    has_zoneinfo_database = False
    nulls_order_largest = True
    supports_mixed_date_datetime_comparisons = False
    supports_tablespaces = False
    supports_sequence_reset = False
    atomic_transactions = False
    supports_foreign_keys = False
    supports_column_check_constraints = False
    supports_select_for_update_with_limit = False
    supports_transactions = False
    supports_stddev = False


class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = '.'.join(__name__.split('.')[:-1]) + '.compiler'

    def quote_name(self, name):
        return name

    def no_limit_value(self):
        return -1


class DatabaseValidation(BaseDatabaseValidation):
    pass


class DatabaseIntrospection(BaseDatabaseIntrospection):
    pass


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = 'jasmin_ldap'

    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations
    validation_class = DatabaseValidation

    # We have implemented our own compiler, so the operators need to look like SQL
    operators = {
        'exact': '= %s',
        'iexact': '= UPPER(%s)',
        'contains': 'LIKE %s',
        'icontains': 'LIKE UPPER(%s)',
        'startswith': 'LIKE %s',
        'endswith': 'LIKE %s',
        'istartswith': 'LIKE UPPER(%s)',
        'iendswith': 'LIKE UPPER(%s)',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.autocommit = True
        self._servers = ServerPool(
            self.settings_dict['PRIMARY'],
            self.settings_dict.get('REPLICAS', [])
        )
        self._bind_dn = self.settings_dict.get('USER', '')
        self._bind_pass = self.settings_dict.get('PASSWORD', '')

    def ensure_connection(self):
        # This is a NOOP
        pass

    def _set_autocommit(self, autocommit):
        # This is a NOOP
        pass

    def close(self):
        self.validate_thread_sharing()

    def _connection(self, mode):
        return Connection.create(self._servers, self._bind_dn, self._bind_pass, mode)

    @contextlib.contextmanager
    def create_query(self, base_dn):
        """
        This function is designed to be used as a context manager in a with statement, e.g.:

        ::

            with conn.create_query(base_dn) as query:
                # ... do stuff with query

        This ensures that the underlying LDAP connection is closed correctly.
        """
        logger.debug('Creating query', stack_info = True)
        with self._connection(Connection.MODE_READONLY) as conn:
            yield LDAPQuery(conn, base_dn)

    def create_entry(self, dn, attributes):
        with self._connection(Connection.MODE_READWRITE) as conn:
            return conn.create_entry(dn, attributes)

    def update_entry(self, dn, attributes):
        with self._connection(Connection.MODE_READWRITE) as conn:
            return conn.update_entry(dn, attributes)

    def check_entry_password(self, dn, password):
        try:
            # Just create a connection and close it straight away
            # If there is an authentication error, it will throw
            Connection.create(self._servers, dn, password).close()
            return True
        except AuthenticationError:
            return False

    def set_entry_password(self, dn, password):
        with self._connection(Connection.MODE_READWRITE) as conn:
            return conn.set_entry_password(dn, password)

    def delete_entry(self, dn):
        with self._connection(Connection.MODE_READWRITE) as conn:
            return conn.delete_entry(dn)
