"""
This module provides a Django ``SQLCompiler`` implementation that can convert
a Django query into an ``jasmin_ldap.Query`` for execution on an LDAP database.
"""

__author__ = "Matt Pryor"
__copyright__ = "Copyright 2015 UK Science and Technology Facilities Council"

import functools, operator
from collections import OrderedDict

from django.db.models import aggregates, expressions, lookups
from django.db.models.sql import compiler, where

from jasmin_ldap.filters import Expression, AndNode, OrNode, NotNode
from jasmin_ldap import annotations as ldap_annot, aggregations as ldap_aggr


class SQLCompiler(compiler.SQLCompiler):
    """
    SQL compiler that knows how to cross compile an SQL query to a user query.
    """

    def _compile(self, expr):
        """
        Cross-compiles a Django where expression into a jasmin_ldap filter expression.
        """
        if isinstance(expr, lookups.Lookup):
            if isinstance(expr.lhs, expressions.Col):
                return Expression(expr.lhs.target.column, expr.lookup_name, expr.rhs)
            else:
                raise TypeError('Filtering on annotations is not supported')
        elif isinstance(expr, where.WhereNode):
            children = expr.children
            if len(children) == 1:
                node = self._compile(children[0])
            elif expr.connector == where.AND:
                node = AndNode(*[self._compile(c) for c in expr.children])
            elif expr.connector == where.OR:
                node = OrNode(*[self._compile(c) for c in expr.children])
            else:
                raise TypeError('Unsupported connector: {}'.format(expr.connector))
            if expr.negated:
                node = NotNode(node)
            return node
        raise TypeError('Unsupported node: {}'.format(repr(expr)))

    def execute_sql(self, result_type = compiler.MULTI, chunked_fetch = False):
        if result_type not in [compiler.SINGLE, compiler.MULTI]:
            return None

        extra_select, order_by, group_by = self.pre_sql_setup()

        # Gather info about how to build the query
        q_annots = OrderedDict()  # alias => annotation mapping, ordered
        q_aggregates = OrderedDict()  # alias => aggregate mapping, ordered
        fields = []  # Field names to extract from the query, in order
        for expr, _, alias in self.select + extra_select:
            if isinstance(expr, expressions.Col):
                # This is a field extraction
                fields.append(expr.target.column)
                continue
            elif isinstance(expr, aggregates.Aggregate):
                # We only support aggregates with one source expression
                if len(expr.source_expressions) == 1:
                    se = expr.source_expressions[0]
                    # Explicitly support count for the whole query
                    if isinstance(expr, aggregates.Count) and  \
                       isinstance(se, expressions.Star):
                        q_aggregates[alias] = ldap_aggr.Count()
                        continue
                    expr_name = expr.__class__.__name__
                    # Get the target field from the source expression
                    if isinstance(se, expressions.Col):
                        name = alias or se.target.name + '__' + expr_name.lower()
                        target = se.target.column
                    elif isinstance(se, expressions.Ref):
                        name = alias or se.target.name + '__' + expr_name.lower()
                        target = se.refs
                    else:
                        raise NotImplementedError(
                                  'Unsupported usage: {}'.format(repr(expr)))
                    # We rely on the LDAP annotations and aggregations having the
                    # same names as the Django ones
                    if expr.is_summary:
                        # If is_summary = True, it is an aggregation
                        try:
                            q_aggregates[name] = getattr(ldap_aggr, expr_name)(target)
                            continue
                        except AttributeError:
                            pass
                    else:
                        # Otherwise, it is an annotation
                        try:
                            q_annots[name] = getattr(ldap_annot, expr_name)(target)
                            fields.append(name)
                            continue
                        except AttributeError:
                            pass
            raise NotImplementedError('Unsupported usage: {}'.format(repr(expr)))

        # Make the LDAP query
        with self.connection.create_query(self.query.model.base_dn) as query:
            # Apply any annotations
            if q_annots:
                query = query.annotate(**q_annots)

            # Add filters for the search classes of the model
            search_classes = self.query.model.search_classes
            if search_classes is None:
                search_classes = self.query.model.object_classes
            for oc in search_classes:
                query = query.filter(objectClass = oc)
            # Compile the where expression to a filter and apply
            if self.query.where:
                query = query.filter(self._compile(self.query.where))

            # Apply the field extraction (if no fields are given, select them all)
            if fields:
                query = query.select(*fields)

            # Make the query distinct if the query is distinct
            if self.query.distinct:
                query = query.distinct()

            # Apply any orderings
            if order_by:
                orderings = []
                for o, _ in order_by:
                    if isinstance(o.expression, expressions.Col):
                        attribute = o.expression.target.column
                    elif isinstance(o.expression, expressions.Ref):
                        attribute = o.expression.refs
                    else:
                        raise NotImplementedError('Unsupported expression: {}'.format(repr(o)))
                    if o.descending:
                        attribute = '-' + attribute
                    orderings.append(attribute)
                query = query.order_by(*orderings)

            # Apply any limits
            if self.query.low_mark or self.query.high_mark:
                query = query[self.query.low_mark:self.query.high_mark]

            if result_type == compiler.SINGLE:
                # If we have aggregations, use them instead
                if q_aggregates:
                    result = query.aggregate(**q_aggregates)
                    return [result.get(n) for n in q_aggregates.keys()]
                result = query.one()
                if result is not None:
                    return [result.get(f, []) for f in fields]
                else:
                    return None
            else:
                # When result type is MULTI, the return value should be a list of
                # chunks of results
                # We treat all the results as a single chunk
                return [[[r.get(f, []) for f in fields] for r in query]]

    def has_results(self):
        return self.execute_sql(compiler.SINGLE) is not None


class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    def execute_sql(self, result_type = compiler.MULTI):
        raise NotImplementedError('Bulk insert is not supported for LDAP')


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    def execute_sql(self, result_type = compiler.MULTI):
        raise NotImplementedError('Bulk update is not supported for LDAP')


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    def execute_sql(self, result_type = compiler.MULTI):
        raise NotImplementedError('Bulk delete is not supported for LDAP')


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass
