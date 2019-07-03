# Copyright 2019-present Kensho Technologies, LLC.
"""TODO:

(Possibly) break the MergedSchema class into functions that do the stuff (the logic) and the output
    strings and mapping (the result). Even if later the logic changes, can still use result; the
    clients using the api don't need to know that the logic has changed even. Not everything has to
    be a class, passing a MergedSchema along with all its code inside is no good (too fat).
Be very loud and clear about checking the validity of things.
Design things so that it's impossible to be in a bad state.


Always add in the stitch directive as a special case for now
"""


from collections import namedtuple
import copy

from graphql import parse
from graphql.language import ast as ast_classes
from graphql.language.printer import print_ast
from graphql.language.visitor import Visitor, visit
import six

from .merge_schema_asts import merge_schema_asts
from .utils import SchemaError, get_schema_data


# Change MergedSchema to a lightweight namedtuple, and have a function produce it

class MergedSchema(object):
    # TODO: use helpers in compiler like merge_disjoint_dict -- fail on assertions easier to
    # deal with than fails on wrong answers
    def __init__(self, schemas_info):
        """Check that input schemas do not contain name clashes, then merge.

        Merged schema will contain all type, interface, enum, scalar, and directive definitions
        from input schemas. Its root fields will be the union of all root fields from input
        schemas.

        The name of its root query type will be the name of the root query type in the first
        input schema.

        Args:
            schemas_info: OrderedDict where keys are schema_identifiers, and values are
                          RenamedSchema objects. Schemas will be merged in order

        Raises:
            SchemaError if any schema contains extensions, or if a renamed type causes a name
                conflict
        """
        # TODO: can only take in RenamedSchemas? Also take in MergedSchemas? Remove the
        # RenamedSchema entirely?
        # If take in MergedSchemas, do the MergedSchemas also have schema identifiers?
        # Separate function that takes in list of MergedSchemas and produces one MergedSchema?
        if len(schemas_info) == 0:
            raise ValueError('Received 0 schemas to merge')

        self.reverse_name_id_map = {}  # dict mapping new name to (original name, schema id)
        self.reverse_root_field_id_map = {}  # dict mapping new field to (original name, schema id)
        self.merged_schema = None  # type: Document

        # TODO: Later on, also check the definitions of directives don't conflict
        self._check_no_conflict(schemas_info.values())

        for schema_identifier, renamed_schema in six.iteritems(schemas_info):
            self._merge_schema(schema_identifier, renamed_schema)

    def demangle_query(self, query_string, schema_identifier):
        # Separate this out into a normal function
        """Demangle all types in query_string from renames to originals.

        Args:
            query_string: string
            schema_identifier: string

        Raises:
            SchemaError if a type or root field in query string cannot be found in the schema that
                schema_identifier points to

        Returns:
            query string where type names are demangled
        """
        ast = parse(query_string)
        # need to translate back both root fields and types. how to distinguish?
        # for example, maybe 'human: Human' got renamed to 'NewHuman: NewHuman' for some reason,
        # which is perfectly legal. Which one does NewHuman mean?
        # is it only the root of the query that can be a root field?
        # some fields are not translated, such as alias or various non-root field names
        visitor = DemangleQueryVisitor(self.reverse_name_id_map, self.reverse_root_field_id_map,
                                       schema_identifier)
        visit(ast, visitor)
        return print_ast(ast)

    def get_original_type(self, new_name, schema_identifier):
        """Get the original name of the input object renamed name.

        Args:
            new_name: string, renamed name of the type/enum/interface/scalar
            schema_identifier: string, the identifier of the schema that the type is from

        Raises:
            SchemaError if new_name is not found, or if it's found but has the wrong
                schema_identifier

        Returns:
            string, the original name of the type
        """
        if new_name not in self.reverse_name_id_map:
            raise SchemaError('Type "{}" not found.'.format(new_name))
        old_name, recorded_schema_identifier = self.reverse_name_id_map[new_name]
        if schema_identifier != recorded_schema_identifier:
            raise SchemaError(
                'Type "{}" is from schema "{}" under name "{}", not from "{}".'.format(
                    new_name, recorded_schema_identifier, old_name, schema_identifier
                )
            )
        return old_name

    @property
    def schema_string(self):
        """Return a string describing the merged schema in GraphQL Schema Language."""
        return print_ast(self.merged_schema)

    def _check_no_conflict(self, renamed_schemas):
        """Check the input schemas don't contain name clashes.

        Args:
            renamed_schemas: set-like object of RenamedSchemas

        Raises:
            SchemaError if there is any repetition among the set of new names of
                types/interfaces/enums and the names of scalars
        """
        new_names = set()
        scalars = set()
        for renamed_schema in renamed_schemas:
            if not new_names.isdisjoint(renamed_schema.reverse_name_map.keys()):
                raise SchemaError('{} defined more than once'.format(
                    new_names.intersection(renamed_schema.reverse_name_map.keys())
                ))
            new_names.update(renamed_schema.reverse_name_map.keys())
            schema_data = get_schema_data(renamed_schema.schema_ast)
            scalars.update(schema_data.scalars)
        if not new_names.isdisjoint(scalars):
            raise SchemaError('{} defined more than once'.format(
                new_names.intersection(scalars)
            ))

    def _merge_schema(self, schema_identifier, renamed_schema):
        """Incorporate renamed_schema, updating merged_schema and reverse maps.

        Args:
            schema_identifier: string
            renamed_schema: RenamedSchema
        """
        ast = copy.deepcopy(renamed_schema.schema_ast)
        if self.merged_schema is None:  # first schema
            self.merged_schema = ast
        else:
            self._remove_duplicates(ast)
            self.merged_schema = merge_schema_asts(self.merged_schema, ast)

        for new_name, original_name in six.iteritems(renamed_schema.reverse_name_map):
            self.reverse_name_id_map[new_name] = (original_name, schema_identifier)
        for new_name, original_name in six.iteritems(renamed_schema.reverse_root_field_map):
            self.reverse_root_field_id_map[new_name] = (original_name, schema_identifier)

    def _remove_duplicates(self, ast):
        """Remove any scalars or directives already defined from the ast."""
        schema_data = get_schema_data(self.merged_schema)

        filtered_definitions = []
        for definition in ast.definitions:
            if (
                isinstance(definition, ast_classes.ScalarTypeDefinition) and
                definition.name.value in schema_data.scalars
            ):
                continue
            if (
                isinstance(definition, ast_classes.DirectiveDefinition) and
                definition.name.value in schema_data.directives
            ):
                continue
            filtered_definitions.append(definition)

        ast.definitions = filtered_definitions  # is this ok? need to copy contents instead?


class DemangleQueryVisitor(Visitor):
    def __init__(self, reverse_name_id_map, reverse_root_field_id_map, schema_identifier):
        pass

    # Want to rename two things: the first level selection set field names (root fields)
    # and NamedTypes (e.g. in fragments)
    # Should do those in two steps
    # TODO
    # First step doesn't need visitor. Just iterate over selection set like with dedup
    # Second step uses very simple visitor that transforms all NamedTypes that are not scalars
    # or builtins?


# TODO: implement query demangling
# TODO: look at code for splitting queries and see where the namespace fits in
# TODO: provide rename only on collision as an option
# TODO: cross server edge descriptor
