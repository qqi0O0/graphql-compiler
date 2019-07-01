"""
TODO: 

(Possibly) break the MergedSchema class into functions that do the stuff (the logic) and the output
    strings and mapping (the result). Even if later the logic changes, can still use result; the
    clients using the api don't need to know that the logic has changed even. Not everything has to
    be a class, passing a MergedSchema along with all its code inside is no good (too fat).
Change the RenameSchemaVisitor from bottom to top (child inspecting parent path) to top to bottom
    (parent renames children on leave)
Probably will need to separate out the RenameSchemaVisitor to a new file since it'll get very big.
    Cover all available types, fail loudly for ones that shouldn't appear.
Be very loud and clear about checking the validity of things.
Design things so that it's impossible to be in a bad state.


Look up the visit_and_rename function maybe? Seems like a typical visitor pattern.

"""


from collections import OrderedDict
from graphql import build_ast_schema, extend_schema, parse
from graphql.error import GraphQLError
from graphql.language.visitor import Visitor, visit
from graphql.language.ast import TypeExtensionDefinition
from graphql.language.printer import print_ast
from graphql.utils.schema_printer import print_schema
import six
from textwrap import dedent


class SchemaError(Exception):
    pass


class SchemaTypeConflictError(SchemaError):
    pass


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
                         types, interfaces, enums, and root fields
        """
        self.schema_string = ''
        self.reverse_name_map = {}  # maps new names to original names
        self.reverse_root_field_map = {}  # maps new field names to original field names

        self._check_schema_valid(schema_string)
        self._rename_schema(schema_string, rename_func)

    def _check_schema_valid(self, schema_string):
        """Check that input schema is a valid standalone schema without extensions.

        Args:
            schema_string: string

        Raises:
            SchemaError if input schema is not a valid input schema.
        """
        try:
            ast = parse(schema_string)
            build_ast_schema(ast)
        except Exception:  # Can't be more specific -- see graphql/utils/build_ast_schema.py:187
            raise SchemaError('Input schema does not define a valid schema.')

        # Extensions not allowed in input schemas
        schema_data = _get_schema_data(ast)
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
                support extensions (build_ast_schema eats extensions)
            SchemaTypeConflictError if a renamed type in the schemas string causes a type name
                conflict, between types/interfaces/enums/scalars

        Return:
            string, the new renamed schema
        """
        ast = parse(schema_string)

        # Get data about the schema
        schema_data = _get_schema_data(ast)

        query_type_name = schema_data.query_type

        # Rename types, interfaces, enums
        self._rename_types(ast, rename_func, schema_data)

        # Rename root fields
        self._rename_root_fields(ast, rename_func, query_type_name)

        # Set schema string to renamed version
        self.schema_string = print_ast(ast)

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
    def __init__(self, schemas_info):
        """Check that input schemas do not contain name clashes, then merge.

        Args:
            schemas_info: OrderedDict where keys are schema_identifiers, and values are 
                          RenamedSchema objects. Schemas will be merged in order

        Raises:
            SchemaError if any schema contains extensions
            SchemaTypeConflictError if a renamed type in any schemas string causes a name conflict
        """
        if len(schemas_info) == 0:
            raise ValueError('Received 0 schemas to merge')

        # NOTE: change the below to a dictionary where keys are schema_ids, and the contents are
        # another dictionary of new names to old names? Makes sense for translating back queries
        # as well. 
        # the scalars and directives sets would just be local fields in the function that merges
        # schemas by taking in an ordereddict of schema name and RenamedSchemas, and outputs some
        # kind of MergedSchema that's similar to a RenamedSchema but has the schema id field in
        # its name/field maps
        self.reverse_name_id_map = {}  # dict mapping new name to (original name, schema id)
        self.reverse_root_field_id_map = {}  # dict mapping new field name to 
                                             # (original field name, schema id)
        self.query_type = 'RootSchemaQuery'
        self.merged_schema = None

        # TODO: Later on, also check the definitions of directives don't conflict
        self._check_validity(schemas_info.values())

        for schema_identifier, renamed_schema in six.iteritems(schemas_info):
            self._merge_schema(schema_identifier, renamed_schema)

    def demangle_query(self, query_string, schema_identifier):
        """Demangle all types in query_string from renames to originals.

        Args:
            query_string: string
            schema_identifier: string

        Raises:
            SchemaError if a type in query string cannot be found in the schema that
                schema_identifier points to

        Returns:
            query string where type names are demangled
        """
        ast = parse(query_string)
        # need to translate back both root fields and types. how to distinguish?
        # for example, maybe 'human: Human' got renamed to 'NewHuman: NewHuman' for some reason,
        # which is perfectly legal. Which one does NewHuman mean? 
        # is it only the root of the query that can be a root field? 
        # some fields are not translated, such as alias
        pass

    def get_original(self, new_name):
        """Get the original name and schema identifier of the input object renamed name.

        Args:
            new_name: string, renamed name of the type/enum/interface/scalar in question

        Raises:
            SchemaError if no type in the namespace has the input renamed name

        Returns:
            Tuple (string, string), the original name of the input, and the schema_identifier of
                the schema the input type belongs to
        """
        return self.reverse_name_id_map[new_name]

    def get_schema_string(self):
        """Return a string describing the merged schema in GraphQL Schema Language."""
        return print_schema(self.merged_schema)

    def _check_validity(self, renamed_schemas):
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
            schema_data = _get_schema_data(parse(renamed_schema.schema_string))
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
        schema_data = _get_schema_data(ast)
        if self.merged_schema is None:  # first schema
            visitor = ModifyQueryTypeVisitor(schema_data.query_type, self.query_type,
                                             change_to_extension=False)
            visit(ast, visitor)
            self.merged_schema = build_ast_schema(ast)
        else:
            visitor = ModifyQueryTypeVisitor(schema_data.query_type, self.query_type,
                                             change_to_extension=True)
            visit(ast, visitor)
            self._remove_duplicates(ast)
            self.merged_schema = extend_schema(self.merged_schema, ast)

        for new_name, original_name in six.iteritems(renamed_schema.reverse_name_map):
            self.reverse_name_id_map[new_name] = (original_name, schema_identifier)
        for new_name, original_name in six.iteritems(renamed_schema.reverse_root_field_map):
            self.reverse_root_field_id_map[new_name] = (original_name, schema_identifier)

    def _remove_duplicates(self, ast):
        """Remove any scalars already defined from the ast, update internal records."""
        schema_data = _get_schema_data(parse(print_schema(self.merged_schema)))
        visitor = RemoveDuplicatesVisitor(schema_data.scalars, schema_data.directives)
        visit(ast, visitor)


class SchemaData(object):
    def __init__(self):
        self.query_type = None
        self.scalars = set()
        self.directives = set()
        self.has_extension = False


class RenameSchemaVisitor(Visitor):
    """Used to traverse a Document AST, editing the names of nodes on the way."""
    def __init__(self, rename_func, query_type, scalar_types):
        self.rename_func = rename_func  # callable that takes string to string
        self.reverse_name_map = {}  # Dict[str, str], from new name to original name
        self.query_type = query_type
        self.scalar_types = scalar_types
        self.builtin_types = {'String', 'Int', 'Float', 'Boolean', 'ID'}

    def _match_end_of_list(self, full_list, pattern):
        """Check whether the end of full_list matches the pattern.

        The list pattern may contain None, which matches against anything in the full_list.
        If pattern is longer than the full_list, and some beginning element that lies outside the
        full_list is not None, then the lists are considered to not match. 

        Args:
            full_list: list whose elements are int or str
            pattern: list whose elements are int, str, or None

        Return:
            True if the end of full_list matches pattern, False otherwise
        """
        for back_index in range(1, len(pattern) + 1):
            if pattern[-back_index] is not None:
                if back_index > len(full_list) or full_list[-back_index] != pattern[-back_index]:
                    return False
        return True

    def _need_rename(self, node, key, parent, path, ancestors):
        """Check that the node should be renamed.

        In particular, check that the node is not a builtin scalar type, and that the structure of
        the path is so that the node should be renamed.

        Args:
            node: Name type (inheriting from Node type), the node that may be renamed
            path: list of ints and strings, has the format of path in the argument of enter

        Return:
            True if the node should be renamed, False otherwise
        """
        # Path along may not be quite enough to know the structure for certain
        name_string = node.value
        if (
            name_string in self.builtin_types or
            name_string in self.scalar_types or
            name_string == self.query_type
        ):
            return False
        # InterfaceTypeDefinition, EnumTypeDefinition, or ObjectTypeDefinition
        if self._match_end_of_list(path, ['definitions', None, 'name']):
            return True
        # Interface implemented by type, e.g. 'Character' in 'type Human implementing Character'
        if self._match_end_of_list(path, ['interfaces', None, 'name']):
            return True
        # NamedType, e.g. 'Character' in 'friend: Character'
        if self._match_end_of_list(path, ['type', 'name']):
            return True
        # Union, e.g. 'Human' in 'union HumanOrDroid = Human | Droid
        if self._match_end_of_list(path, ['types', None, 'name']):
            return True
        # EnumValueDefinition, e.g. 'NEWHOPE' in 'Enum Episode { NEWHOPE }'
        if self._match_end_of_list(path, ['values', None, 'name']):
            return False
        # InputValueDefinition, e.g. 'episode' in 'hero(episode: Episode): Character'
        #                       e.g. 'source_field' in '@stitch(source_field: "a", sink_field: "b")'
        if self._match_end_of_list(path, ['arguments', None, 'name']):
            return False
        # Directive, e.g. 'stitch' in '@stitch(source_field: "a", sink_field: "b")' on a field
        if self._match_end_of_list(path, ['directives', None, 'name']):
            return False
        # FieldDefinition, e.g. 'friend' in 'friend: Character'
        # fields of the query type will be renamed later
        if self._match_end_of_list(path, ['fields', None, 'name']):
            return False
        # TODO: any missing cases
        raise AssertionError("Incomplete!\nPath: {}\n\nNode: {}".format(path, node))

    def _rename_name_add_to_record(self, node):
        """Rename the value of the node, and add the name mapping to reverse_name_map."""
        name_string = node.value
        new_name_string = self.rename_func(name_string)
        node.value = new_name_string
        if (
            new_name_string in self.reverse_name_map and
            self.reverse_name_map[new_name_string] != name_string
        ):
            raise SchemaError(
                '{} and {} are both renamed to {}'.format(
                    name_string, self.reverse_name_map[new_name_string], new_name_string
                )
            )
        if new_name_string in self.scalar_types:
            raise SchemaError(
                '{} was renamed to {}, clashing with scalar {}'.format(
                    name_string, new_name_string, new_name_string
                )
            )
        if new_name_string in self.builtin_types:
            raise SchemaError(
                '{} was renamed to {}, clashing with builtin {}'.format(
                    name_string, new_name_string, new_name_string
                )
            )

        self.reverse_name_map[new_name_string] = name_string

    def _skip_branch(self, node, *args):
        """Do not traverse down the current node."""
        return False

    # Methods named enter_TYPENAME will be called on a node of TYPENAME upon entering it in
    # traversal. Similarly, methods named leave_TYPENAME will be called upon leaving a node.
    # For a complete list of possibilities for TYPENAME, see QUERY_DOCUMENT_KEYS in file
    # graphql/language/visitor_meta.py

    def enter_Name(self, node, key, parent, path, ancestors):
        """If structure of node satisfies requirements, rename node."""
        if self._need_rename(node, key, parent, path, ancestors):
            self._rename_name_add_to_record(node)

    enter_ScalarTypeDefinition = enter_DirectiveDefinition = _skip_branch


class RenameRootFieldsVisitor(Visitor):
    def __init__(self, rename_func, query_type_name):
        self.in_query_type = False
        self.reverse_field_map = {}
        self.rename_func = rename_func
        self.query_type_name = query_type_name

    def enter_ObjectTypeDefinition(self, node, *args):
        """If entering query type, set flag to True."""
        if node.name.value == self.query_type_name:
            self.in_query_type = True

    def leave_ObjectTypeDefinition(self, node, key, parent, path, ancestors):
        """If leaving query type, set flag to False."""
        if node.name.value == self.query_type_name:
            self.in_query_type = False

    def enter_FieldDefinition(self, node, *args):
        """If entering field under query type, rename and add to reverse map."""
        if self.in_query_type:
            field_name = node.name.value
            new_field_name = self.rename_func(field_name)
            node.name.value = new_field_name
            if (
                new_field_name in self.reverse_field_map and
                self.reverse_field_map[new_field_name] != field_name
            ):
                raise SchemaError(
                    '{} and {} are both renamed to {}'.format(
                        field_name, self.reverse_field_map[new_field_name], new_field_name
                    )
                )
            self.reverse_field_map[new_field_name] = field_name


class ModifyQueryTypeVisitor(Visitor):
    """Rename query type and change to extension."""
    def __init__(self, cur_query_type_name, target_query_type_name, change_to_extension):
        self.cur_query_type_name = cur_query_type_name
        self.target_query_type_name = target_query_type_name
        self.change_to_extension = change_to_extension

    def enter_OperationTypeDefinition(self, node, *args):
        """If entering query definition, rename query type."""
        node.type.name.value = self.target_query_type_name

    def enter_ObjectTypeDefinition(self, node, key, parent, path, ancestors):
        """If entering query type, rename query type, optionally change to extension."""
        if node.name.value == self.cur_query_type_name:
            node.name.value = self.target_query_type_name
            if self.change_to_extension:
                new_node = TypeExtensionDefinition(definition = node)
                parent[key] = new_node


class RemoveDuplicatesVisitor(Visitor):
    """Remove repeated scalar or directive definitions."""
    def __init__(self, existing_scalars, existing_directives):
        self.existing_scalars = existing_scalars
        self.existing_directives = existing_directives

    def enter_ScalarTypeDefinition(self, node, key, parent, path, ancestors):
        """If scalar has already been defined, remove it from the ast."""
        if node.name.value in self.existing_scalars:
            parent[key] = None

    def enter_DirectiveDefinition(self, node, key, parent, path, ancestors):
        """If directive has already been defined, remove it from the ast."""
        if node.name.value in self.existing_directives:
            parent[key] = None


class GetSchemaDataVisitor(Visitor):
    """Gather information about the schema before making any transforms."""
    def __init__(self):
        self.schema_data = SchemaData()

    def enter_TypeExtensionDefinition(self, node, *args):
        self.schema_data.has_extension = True

    def enter_OperationTypeDefinition(self, node, *args):
        if node.operation == 'query':  # might add mutation and subscription options
            self.schema_data.query_type = node.type.name.value

    def enter_ScalarTypeDefinition(self, node, *args):
        self.schema_data.scalars.add(node.name.value)

    def enter_DirectiveDefinition(self, node, *args):
        # NOTE: currently we don't check if the definitions of the directives agree
        # any directive that comes after one of the same one is simply erased, even if it
        # has a different definition
        self.schema_data.directives.add(node.name.value)


def _get_schema_data(ast):
    """Get schema data of input ast.

    Args:
        ast: Document

    Return:
        SchemaData
    """
    # NOTE: currently we're calling this whenever needed, rather than passing the computed
    # schema_data around. This can be optimized if needed
    get_schema_data_visitor = GetSchemaDataVisitor()
    visit(ast, get_schema_data_visitor)
    return get_schema_data_visitor.schema_data




# TODO: implement query demangling
# TODO: look at code for splitting queries and see where the namespace fits in

# TODO: provide rename only on collision as an option


# TODO: cross server edge descriptor?
