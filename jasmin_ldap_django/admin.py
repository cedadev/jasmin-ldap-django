"""
This module provides support in the Django admin for LDAP backends.
"""

__author__ = "Matt Pryor"
__copyright__ = "Copyright 2015 UK Science and Technology Facilities Council"

from django.contrib.admin.utils import lookup_field
from django.contrib.admin.helpers import AdminReadonlyField
from django.utils.encoding import smart_text
from django.utils.html import conditional_escape
from django.core.exceptions import ObjectDoesNotExist

from .models import ListField


# Monkey-patch the admin readonly field to support ListField
_original = AdminReadonlyField.contents
def _contents(self):
    field, obj, model_admin = self.field['field'], self.form.instance, self.model_admin
    try:
        f, attr, value = lookup_field(field, obj, model_admin)
    except (AttributeError, ValueError, ObjectDoesNotExist):
        pass
    else:
        if isinstance(f, ListField):
            if not value:
                return conditional_escape(self.empty_value_display)
            return conditional_escape(', '.join(smart_text(v) for v in value))
    return _original(self)
AdminReadonlyField.contents = _contents
