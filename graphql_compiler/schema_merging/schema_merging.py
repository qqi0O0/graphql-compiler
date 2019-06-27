from graphql import build_ast_schema, extend_schema, parse
from graphql.language.visitor import Visitor, visit, BREAK
from graphql.language.ast import TypeExtensionDefinition
from graphql.utils.schema_printer import print_schema
import six
from textwrap import dedent


class SchemaError(Exception):
    pass


class SchemaTypeConflictError(SchemaError):
    pass


class SchemaTypeNotFoundError(SchemaError):
    pass


class MergedSchema(object):
    def __init__(self, schemas_info):
        """Rename (mangle) types and merge input schemas according to input information.

        Args:
            schemas_info: list of (schema_string, schema_identifier, rename_func)
                          of types (string, string, callable). rename_func may be ommitted to
                          use the defaults. Schemas will be merged in order.
                              schema_string is a schema written in GraphQL schema language
                              schema_identifier is a string that uniquely identifies the schema
                              rename_func is a callable used to convert original type names to new
                                  type names, taking a string of the original type name as its
                                  argument. Defaults to the identity function

        Raises:
            SchemaError if any schema contains extensions
            SchemaTypeConflictError if a renamed type in any schemas string causes a name conflict
        """
        # input is rather inelegant, but that's alright for now
        self.reverse_name_id_map = {}  # dict mapping new name to (original name, schema id)
        self.reverse_root_field_id_map = {}  # dict mapping new field name to 
                                             # (original field name, schema id)
        self.query_type = 'RootSchemaQuery'
        self.scalars = set()
        self.directives = set()

        empty_schema = dedent('''
            schema {
              query: %s
            }

            type %s {
              _: Boolean
            }
        ''' % (self.query_type, self.query_type))

        self.merged_schema = build_ast_schema(parse(empty_schema))

        for schema_info in schemas_info:
            if len(schema_info) == 2:
                schema_string, schema_identifier = schema_info
                modified_ast = self._modify_schema(schema_string, schema_identifier)
                self._merge_schema(modified_ast)
            elif len(schema_info) == 3:
                schema_string, schema_identifier, rename_func = schema_info
                modified_ast = self._modify_schema(schema_string, schema_identifier, rename_func)
                self._merge_schema(modified_ast)
            else:
                raise ValueError('Expected list elements of 2-tuples or 3-tuples.')

    def demangle_query(self, schema_identifier, query_string):
        """Demangle all types in query_string from renames to originals.

        Args:
            query_string: string

        Raises:
            SchemaTypeNotFoundError if a type in query string cannot be found in the schema that
                schema_identifier points to

        Returns:
            query string where type renames are demangled
        """
        pass

    def get_original(self, new_name):
        """Get the original name and schema identifier of the input object renamed name.

        Args:
            new_name: string, renamed name of the type/enum/interface/scalar in question

        Raises:
            SchemaTypeNotFoundError if no type in the namespace has the input renamed name

        Returns:
            Tuple (string, string), the original name of the input, and the schema_identifier of
                the schema the input type belongs to
        """
        return self.reverse_name_id_map[new_name]

    def get_schema_string(self):
        """Return a string describing the merged schema in GraphQL Schema Language."""
        return print_schema(self.merged_schema)

    def _modify_schema(self, schema_string, schema_identifier,
                                 rename_func=lambda name:name):
        """Modify schema so that the output can be directly merged.

        Name and field maps will also be modified.

        The query type will be renamed and changed from a type definition to a renamed
        type extension.

        Note that if the new addition causes name conflicts, schema_namespace may only be partially
        modified, and therefore should be discarded and rebuilt.

        Args:
            schema_string: string, in GraphQL schema language
            schema_identifier: string, identifies the current schema, so that renamed types
                               can be translated back into its original name and schema identifier
            rename_func: callable that converts type names to renamed type names. Takes a string
                         as input and returns a string. Defaults to identity function

        Raises:
            SchemaError if the input schema contains extensions, as the renamer doesn't currently
                support extensions
            SchemaTypeConflictError if a renamed type in the schemas string causes a type name
                conflict in schema_namespace

        Return:
            Document, the ast of the modified schema
        """
        ast = parse(schema_string)  # type: Document

        # Get data about the schema
        schema_data = self._get_schema_data(ast)

        # Extensions not allowed in input schemas
        if schema_data.has_extensions:
            raise SchemaError("Input schemas should not contain extensions")

        cur_query_type_name = schema_data.query_type

        # Traverse the schema AST, renaming types as necessary
        self._rename_types(ast, schema_identifier, rename_func, schema_data)

        # Modify the query type and its fields
        self._modify_query_type(ast, schema_identifier, rename_func, cur_query_type_name,
                                self.query_type)

        # Remove duplicate scalars and directives, update scalar + directive sets
        self._remove_duplicates_and_update(ast, schema_data.scalars, schema_data.directives)

        return ast

    def _get_schema_data(self, ast):
        """Get schema data of input ast.

        Args:
            ast: Document

        Return:
            SchemaData
        """
        get_schema_data_visitor = GetSchemaDataVisitor()
        visit(ast, get_schema_data_visitor)
        schema_data = get_schema_data_visitor.schema_data
        return schema_data

    def _rename_types(self, ast, schema_identifier, rename_func, schema_data):
        """Rename types, enums, interfaces, and more using rename_func.

        Types, interfaces, enum definitions will be renamed. 
        Scalar types, field names inside type definitions, enum values will not be renamed.
        Fields of the query type will later be renamed, but not here.

        Args:
            ast: Document, the schema ast that we modify
            schema_identifier: string
            rename_func: callable, used to rename types, interfaces, enums, etc
            schema_data: SchemaData, information about current schema
        """
        visitor = RenameVisitor(rename_func, schema_data.query_type, schema_data.scalars)
        visit(ast, visitor)  # type: Document

        # Update name map, check for conflicts
        # TODO: what about conflicts between things not renamed, say scalars? 
        # extend_schema will throw a GraphQLError, but should we check for that beforehand? 
        new_name_intersection = (six.viewkeys(self.reverse_name_id_map) & 
                                 six.viewkeys(visitor.reverse_name_map))
        if (len(new_name_intersection) != 0):  # name conflict
            raise SchemaTypeConflictError(
                'The following names have already been used: {}'.format(new_name_intersection)
            )
        else:  # no conflict, update name map
            for new_name, original_name in six.iteritems(visitor.reverse_name_map):
                self.reverse_name_id_map[new_name] = (original_name, schema_identifier)

    def _modify_query_type(self, ast, schema_identifier, rename_func, cur_query_type_name,
                           target_query_type_name):
        """Change query type to extension, rename query type and its fields.

        Args:
            ast: Document, the schema ast that we modify
            schema_identifier: string
            rename_func: callable, used to rename fields of the query type
            cur_query_type_name: string, name of the query type, e.g. 'RootSchemaQuery'
            target_query_type_name: string, what to rename the query type to
        """
        visitor = ModifyQueryTypeVisitor(rename_func, cur_query_type_name, target_query_type_name)
        visit(ast, visitor)

        # Update field map, check for conflicts
        new_field_name_intersection = (six.viewkeys(self.reverse_root_field_id_map) & 
                                       six.viewkeys(visitor.reverse_field_map))
        if (len(new_field_name_intersection) != 0):  # name conflict
            raise SchemaTypeConflictError(
                'The following field renames have already been '
                'used: {}'.format(new_field_name_intersection)
            )
        else:  # no conflict, update field map
            for new_field_name, original_field_name in six.iteritems(visitor.reverse_field_map):
                self.reverse_root_field_id_map[new_field_name] = \
                    (original_field_name, schema_identifier)

    def _remove_duplicates_and_update(self, ast, new_scalars, new_directives):
        """Remove any scalars already defined from the ast, update internal records."""
        visitor = RemoveDuplicatesVisitor(self.scalars, self.directives)
        visit(ast, visitor)
        self.scalars.update(new_scalars)
        self.directives.update(new_directives)

    def _merge_schema(self, ast):
        """Merge input schema into merged_schema.

        Args: 
            ast: Document, representing the new input schema
        """
        # TODO: cross service edges?
        self.merged_schema = extend_schema(self.merged_schema, ast)

    def _add_type(self, original_name, new_name, schema_identifier):
        """Add new type to namespace.

        Args:
            original_name: string, name of the type in its own schema
            new_name: string, renamed name of the function
            schema_identifier: string, identifies the schema that the type came from
        
        Raises:
            SchemaTypeConflictError if the new addition's new_name conflicts with the renamed name
                of an existing type in the namespace
        """
        pass


class SchemaData(object):
    def __init__(self):
        self.query_type = None
        self.scalars = set()
        self.directives = set()
        self.has_extension = False


class RenameVisitor(Visitor):
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
        if self._match_end_of_list(path, ['arguments', None, 'name']):
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
        self.reverse_name_map[new_name_string] = name_string

    # Methods named enter_TYPENAME will be called on a node of TYPENAME upon entering it in
    # traversal. Similarly, methods named leave_TYPENAME will be called upon leaving a node.
    # For a complete list of possibilities for TYPENAME, see QUERY_DOCUMENT_KEYS in file
    # graphql/language/visitor_meta.py

    def enter_Name(self, node, key, parent, path, ancestors):
        """If structure of node satisfies requirements, rename node."""
        if self._need_rename(node, key, parent, path, ancestors):
            self._rename_name_add_to_record(node)

    def skip_branch(self, node, *args):
        """Do not traverse down the current node."""
        return False

    enter_ScalarTypeDefinition = enter_DirectiveDefinition = skip_branch

#    enter_NamedType = enter_InterfaceTypeDefinition = enter_EnumTypeDefinition = \
#        enter_ObjectTypeDefinition = rename_name_add_to_record
    
#    enter_Name = rename_name
#    enter_EnumValueDefinition = skip_branch
#    enter_FieldDefinition = skip_branch



class ModifyQueryTypeVisitor(Visitor):
    """First rename fields, then rename query type and change to extension."""
    def __init__(self, rename_func, cur_query_type_name, target_query_type_name):
        self.in_query_type = False
        self.reverse_field_map = {}
        self.rename_func = rename_func
        self.cur_query_type_name = cur_query_type_name
        self.target_query_type_name = target_query_type_name

    def enter_OperationTypeDefinition(self, node, *args):
        """If entering query definition, rename query type."""
        node.type.name.value = self.target_query_type_name

    def enter_ObjectTypeDefinition(self, node, *args):
        """If entering query type, set flag to True."""
        if node.name.value == self.cur_query_type_name:
            self.in_query_type = True

    def leave_ObjectTypeDefinition(self, node, key, parent, path, ancestors):
        """If leaving query type, rename query type, change to extension, and stop traversal."""
        if node.name.value == self.cur_query_type_name:
            node.name.value = self.target_query_type_name
            new_node = TypeExtensionDefinition(definition = node)
            parent[key] = new_node
            return BREAK

    def enter_FieldDefinition(self, node, *args):
        """If entering field under query type, rename and add to reverse map."""
        if self.in_query_type:
            field_name = node.name.value
            new_field_name = self.rename_func(field_name)
            node.name.value = new_field_name
            self.reverse_field_map[new_field_name] = field_name


class RemoveDuplicatesVisitor(Visitor):
    """Remove repeated scalar or directive definitions."""
    def __init__(self, existing_scalars, existing_directives):
        self.existing_scalars = existing_scalars
        self.existing_directives = existing_directives

    def enter_ScalarTypeDefinition(self, node, key, parent, path, ancestors):
        if node.name.value in self.existing_scalars:
            parent[key] = None

    def enter_DirectiveDefinition(self, node, key, parent, path, ancestors):
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



# TODO: union types
# TODO: directives on types (how do those exist inside a schema?)
# TODO: implement query demangling 
# TODO: look at code for splitting queries and see where the namespace fits in

# TODO: provide rename only on collision as an option


# TODO: cross server edge descriptor?
