"""
This module provides plumbing to allow the use of a custom Django DB backend that
is backed by a :py:class:`~jasmin_auth.manager.UserManager`.
"""

__author__ = "Matt Pryor"
__copyright__ = "Copyright 2015 UK Science and Technology Facilities Council"

import contextlib

from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.creation import BaseDatabaseCreation

from jasmin_ldap import Server, Connection, AuthenticationError, Query as LDAPQuery


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


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = 'jasmin_ldap'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.charset = "utf-8"
        self.creation = DatabaseCreation(self)
        self.features = DatabaseFeatures(self)
        self.ops = DatabaseOperations(self)
        self.autocommit = True
        self._server = Server(self.settings_dict['SERVER'])
        self._bind_dn = self.settings_dict.get('USER', '')
        self._bind_pass = self.settings_dict.get('PASSWORD', '')

    def ensure_connection(self):
        # This is a NOOP
        pass

    def _set_autocommit(self, autocommit):
        # This is a NOOP
        pass

    def close(self):
        self.validate_thread_sharing()

    def _connection(self):
        return self._server.authenticate(self._bind_dn, self._bind_pass)

    @contextlib.contextmanager
    def create_query(self, base_dn):
        """
        This function is designed to be used as a context manager in a with statement, e.g.:

        ::

            with conn.create_query(base_dn) as query:
                # ... do stuff with query

        This ensures that the underlying LDAP connection is closed correctly.
        """
        with contextlib.closing(self._connection()) as conn:
            yield LDAPQuery(conn, base_dn)

    def create_entry(self, dn, attributes):
        with contextlib.closing(self._connection()) as conn:
            return conn.create_entry(dn, attributes)

    def update_entry(self, dn, attributes):
        with contextlib.closing(self._connection()) as conn:
            return conn.update_entry(dn, attributes)

    def check_entry_password(self, dn, password):
        try:
            # Just create a connection and close it straight away
            # If there is an authentication error, it will throw
            self._server.authenticate(dn, password).close()
            return True
        except AuthenticationError:
            return False

    def set_entry_password(self, dn, password):
        with contextlib.closing(self._connection()) as conn:
            return conn.set_entry_password(dn, password)

    def rename_entry(self, old_dn, new_dn):
        with contextlib.closing(self._connection()) as conn:
            return conn.rename_entry(old_dn, new_dn)

    def delete_entry(self, dn):
        with contextlib.closing(self._connection()) as conn:
            return conn.delete_entry(dn)
