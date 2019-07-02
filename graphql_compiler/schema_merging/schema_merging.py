"""
TODO: 

(Possibly) break the MergedSchema class into functions that do the stuff (the logic) and the output
    strings and mapping (the result). Even if later the logic changes, can still use result; the
    clients using the api don't need to know that the logic has changed even. Not everything has to
    be a class, passing a MergedSchema along with all its code inside is no good (too fat).
Be very loud and clear about checking the validity of things.
Design things so that it's impossible to be in a bad state.


Always add in the stitch directive as a special case for now
"""


from collections import OrderedDict
from graphql import build_ast_schema, parse
from graphql.language.visitor import Visitor, visit
from graphql.language.printer import print_ast
import six
from textwrap import dedent
from .visitors import (RenameSchemaVisitor, RenameRootFieldsVisitor,
                       RemoveDuplicatesVisitor, GetSchemaDataVisitor, get_schema_data)
from .types_util import SchemaError, SchemaData
from .merge_schema_asts import merge_schema_asts


class RenamedSchema(object):
    # TODO: consider split this up into two pieces, change the init to a normal function that
    # returns a RenamedSchema. The constructor for RenamedSchema would then need to check the
    # validity and consistency of the input
    # Move all the renaming part to here
    # Note that I still need to check no rename conflicts -- different types may be renamed to
    # the same thing, or scalars named to types, or stuff like that
    def __init__(self, schema_string, rename_func=lambda name:name):
        """Create a RenamedSchema.

        Args:
            schema_string: string describing a valid schema that does not contain extensions
            rename_func: callable that takes string to string, used to transform the names of
                         types, interfaces, enums, and root fields. Defaults to identity
        """
        self.schema_ast = None  # type: Document
        self.reverse_name_map = {}  # maps new names to original names
        self.reverse_root_field_map = {}  # maps new field names to original field names

        self._check_schema_validity(schema_string)
        self._rename_schema(schema_string, rename_func)

    @property
    def schema_string(self):
        return print_ast(self.schema_ast)

    def _check_schema_validity(self, schema_string):
        """Check that input schema is a valid standalone schema without type extensions.

        Args:
            schema_string: string

        Raises:
            SchemaError if input schema is not a valid input schema.
        """
        try:
            ast = parse(schema_string)
            build_ast_schema(ast)
        except Exception as e:  # Can't be more specific -- see graphql/utils/build_ast_schema.py
            raise SchemaError('Input schema does not define a valid schema.\n'
                              'Message: {}'.format(e))

        # Extensions not allowed in input schemas
        schema_data = get_schema_data(ast)
        if schema_data.has_extension:
            raise SchemaError("Input schemas should not contain extensions")

    def _rename_schema(self, schema_string, rename_func):
        """Rename types/interfaces/enums and root fields 

        Name and field maps will also be modified.

        Args:
            schema_string: string, in GraphQL schema language
            rename_func: callable that converts type names to renamed type names. Takes a string
                         as input and returns a string. Defaults to identity function

        Raises:
            SchemaError if the input schema contains extensions, as the renamer doesn't currently
                support extensions (build_ast_schema eats extensions), or if a renamed type in the
                schemas string causes a type name conflict, between types/interfaces/enums/scalars

        Return:
            string, the new renamed schema
        """
        ast = parse(schema_string)

        # Get data about the schema
        schema_data = get_schema_data(ast)
        query_type_name = schema_data.query_type

        # Rename types, interfaces, enums
        self._rename_types(ast, rename_func, schema_data)

        # Rename root fields
        self._rename_root_fields(ast, rename_func, query_type_name)

        # Set ast to edited version
        self.schema_ast = ast

    def _rename_types(self, ast, rename_func, schema_data):
        """Rename types, enums, interfaces, and more using rename_func.

        Types, interfaces, enum definitions will be renamed. 
        Scalar types, field names inside type definitions, enum values will not be renamed.
        Fields of the query type will later be renamed, but not here.
        ast will be modified as a result

        Args:
            ast: Document, the schema ast that we modify
            rename_func: callable, used to rename types, interfaces, enums, etc
            schema_data: SchemaData, information about current schema

        Raises:
            SchemaError if the rename causes name conflicts
        """
        visitor = RenameSchemaVisitor(rename_func, schema_data.query_type, schema_data.scalars)
        visit(ast, visitor)

        self.reverse_name_map = visitor.reverse_name_map  # no aliasing, visitor goes oos

    def _rename_root_fields(self, ast, rename_func, query_type_name):
        """Change query type to extension, rename query type and its fields.

        Args:
            ast: Document, the schema ast that we modify
            rename_func: callable, used to rename fields of the query type
            query_type_name: string, name of the query type, e.g. 'RootSchemaQuery'
    
        Raises:
            SchemaError if rename causes field names to clash
        """
        visitor = RenameRootFieldsVisitor(rename_func, query_type_name)
        visit(ast, visitor)

        self.reverse_root_field_map = visitor.reverse_field_map  # no aliasing, visitor goes oos


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
        self.reverse_root_field_id_map = {}  # dict mapping new field name to 
                                             # (original field name, schema id)
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
        if not new_name in self.reverse_name_id_map:
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
            schema_data = get_schema_data(parse(renamed_schema.schema_string))
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
        ast = parse(renamed_schema.schema_string)
        schema_data = get_schema_data(ast)
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
        """Remove any scalars already defined from the ast."""
        schema_data = get_schema_data(self.merged_schema)
        visitor = RemoveDuplicatesVisitor(schema_data.scalars, schema_data.directives)
        visit(ast, visitor)




# TODO: implement query demangling
# TODO: look at code for splitting queries and see where the namespace fits in

# TODO: provide rename only on collision as an option


# TODO: cross server edge descriptor?
