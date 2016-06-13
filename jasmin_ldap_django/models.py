"""
This module provides a Django model that can be used for querying and
manipulating JASMIN user accounts.
"""

__author__ = "Matt Pryor"
__copyright__ = "Copyright 2015 UK Science and Technology Facilities Council"

from collections import Iterable

from django.db import connections, models, router
from django.db.models import signals
from django import forms
from django.core.exceptions import ImproperlyConfigured


class ScalarFieldMixin:
    """
    Mixin that can be used with any scalar field class to do the appropriate
    database conversion.
    """
    def from_db_value(self, value, *args, **kwargs):
        return self.to_python(value)

    def to_python(self, value):
        # If the value is an iterable, extract the first element
        if isinstance(value, Iterable) and not isinstance(value, str):
            value = next(iter(value), None)
        return super().to_python(value)

class CharField(ScalarFieldMixin, models.CharField):
    pass

class TextField(ScalarFieldMixin, models.TextField):
    pass

class EmailField(ScalarFieldMixin, models.EmailField):
    pass

class IntegerField(ScalarFieldMixin, models.IntegerField):
    pass

class PositiveIntegerField(ScalarFieldMixin, models.PositiveIntegerField):
    pass


class ListField(models.Field):
    class FormField(forms.CharField):
        def prepare_value(self, value):
            if isinstance(value, Iterable) and not isinstance(value, str):
                return ', '.join(value)
            return value

        def to_python(self, value):
            return [s for s in map(super().to_python, value.split(',')) if s]

    def formfield(self, **kwargs):
        # Use a custom widget that knows how to interpret lists
        defaults = { 'form_class' : self.FormField }
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def from_db_value(self, value, *args, **kwargs):
        return self.to_python(value)

    def to_python(self, value):
        if value is None:
            return []
        elif isinstance(value, Iterable) and not isinstance(value, str):
            return list(value)
        else:
            return [value]


class LDAPQuerySet(models.QuerySet):
    """
    Custom queryset for use with LDAP models.
    """
    def delete(self):
        # Override the delete method to basically iterate and delete each item
        deleted = 0
        for instance in self:
            instance.delete()
            deleted += 1
        return deleted, { self.model._meta.label : deleted }


class LDAPModel(models.Model):
    """
    Base class for all models that live in LDAP databases.
    """
    class Meta:
        abstract = True

    objects = LDAPQuerySet.as_manager()

    base_dn = None
    object_classes = ['top']
    search_classes = None  # None means use object_classes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Check that base_dn is set
        if not self.base_dn:
            raise ImproperlyConfigured('LDAP models must have a base_dn')
        # Check that there is a field mapping to the CN and that field is a PK
        self._cn_field = None
        for field in self._meta.fields:
            if field.column and field.column.lower() == 'cn' and field.primary_key:
                self._cn_field = field.name
        if not self._cn_field:
            raise ImproperlyConfigured(
                'LDAP models must have a primary key field mapping to the CN'
            )

    def _build_dn(self):
        value = getattr(self, self._cn_field)
        return 'cn={},{}'.format(value, self.base_dn) if value else None

    def save(self, using = None):
        # Since there is no database level integrity checking, run the validation
        # before saving
        self.full_clean()

        signals.pre_save.send(sender = self.__class__, instance = self)

        using = using or router.db_for_write(self.__class__, instance = self)
        connection = connections[using]

        # Build the dn and attribute dictionary from the current state
        dn = self._build_dn()
        attrs = {}
        for field in self._meta.fields:
            # If there is no column, it is not a concrete field
            if not field.column: continue
            attrs[field.column] = field.get_db_prep_save(getattr(self, field.name),
                                                         connection = connection)
        # Add the object classes to the attributes
        attrs['objectClass'] = self.object_classes

        if self._state.adding:
            connection.create_entry(dn, attrs)
            created = True
        else:
            connection.update_entry(dn, attrs)
            created = False

        # If there is a _raw_password attribute, do a password update
        raw_password = getattr(self, '_raw_password', None)
        if raw_password:
            connection.set_entry_password(dn, raw_password)

        # Once we have saved, we should no longer be considered in the adding state
        self._state.adding = False
        signals.post_save.send(sender = self.__class__, instance = self,
                                                        created = created)

    def delete(self, using = None, keep_parents = False):
        if not self._state.adding:
            signals.pre_delete.send(sender = self.__class__, instance = self)
            using = using or router.db_for_write(self.__class__, instance = self)
            connection = connections[using]
            connection.delete_entry(self._build_dn())
            signals.post_delete.send(sender = self.__class__, instance = self)

    def check_password(self, raw_password):
        """
        Verifies that the given raw password matches the password for the account.
        """
        # If the entry has not been saved, the password can't possibly be valid
        if self._state.adding:
            return False
        using = router.db_for_read(self.__class__, instance = self)
        connection = connections[using]
        return connection.check_entry_password(self._build_dn(), raw_password)

    def set_password(self, raw_password):
        """
        Sets the password of the account to the given raw password.
        """
        self._raw_password = raw_password
