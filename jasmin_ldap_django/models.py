"""
This module provides a Django model that can be used for querying and
manipulating JASMIN user accounts.
"""

__author__ = "Matt Pryor"
__copyright__ = "Copyright 2015 UK Science and Technology Facilities Council"

from collections import Iterable

from django.db import connections, models, router
from django.db.models import signals, QuerySet as DefaultQuerySet
from django import forms


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

class SlugField(ScalarFieldMixin, models.SlugField):
    pass

class IntegerField(ScalarFieldMixin, models.IntegerField):
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


class QuerySet(DefaultQuerySet):
    def delete(self):
        # Override the delete method to basically iterate and delete each item
        deleted = 0
        for instance in self:
            instance.delete()
            deleted += 1
        return deleted, { self.model._meta.label : deleted }


class LDAPModel(models.Model):
    class Meta:
        abstract = True

    objects = QuerySet.as_manager()

    base_dn = None
    object_classes = ['top']
    search_classes = None  # None means use object_classes

    dn = models.CharField(max_length = 250, editable = False, primary_key = True)

    def _build_dn(self):
        for field in self._meta.fields:
            if field.column and field.column.lower() == 'cn':
                value = getattr(self, field.name)
                return 'cn={},{}'.format(value, self.base_dn) if value else None
        raise TypeError('LDAP models must have a field mapping to the CN')

    def save(self, using = None):
        signals.pre_save.send(sender = self.__class__, instance = self)

        using = using or router.db_for_write(self.__class__, instance = self)
        connection = connections[using]

        # Build the dn and attribute dictionary from the current state
        dn = self._build_dn()
        attrs = {}
        for field in self._meta.fields:
            # If there is no column, it is not a concrete field
            if field.name == 'dn' or not field.column: continue
            attrs[field.column] = field.get_db_prep_save(getattr(self, field.name),
                                                         connection = connection)
        # Add the object classes to the attributes
        attrs['objectClass'] = self.object_classes

        # If the object already has a DN, we are doing an update
        if self.dn:
            # Check if we first need to do a rename
            if dn.lower() != self.dn.lower():
                connection.rename_entry(self.dn, dn)
                self.dn = dn
            # Then do the update
            connection.update_entry(dn, attrs)
            created = False
        # If the object doesn't have a DN, we are doing a create
        else:
            connection.create_entry(dn, attrs)
            self.dn = dn
            created = True

        # If there is a _raw_password attribute, do a password update
        raw_password = getattr(self, '_raw_password', None)
        if raw_password:
            connection.set_entry_password(self.dn, raw_password)

        # Once we have saved, we should no longer be considered in the adding state
        self._state.adding = False
        signals.post_save.send(sender = self.__class__, instance = self,
                                                        created = created)

    def delete(self, using = None, keep_parents = False):
        if self.dn:
            signals.pre_delete.send(sender = self.__class__, instance = self)
            using = using or router.db_for_write(self.__class__, instance = self)
            connection = connections[using]
            connection.delete_entry(self.dn)
            signals.post_delete.send(sender = self.__class__, instance = self)

    def check_password(self, raw_password):
        """
        Verifies that the given raw password matches the password for the account.
        """
        # If the entry has not been saved, the password can't possibly be valid
        if not self.dn:
            return False
        using = router.db_for_read(self.__class__, instance = self)
        connection = connections[using]
        return connection.check_entry_password(self.dn, raw_password)

    def set_password(self, raw_password):
        """
        Sets the password of the account to the given raw password.
        """
        self._raw_password = raw_password
