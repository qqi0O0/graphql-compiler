from graphql.language.visitor import Visitor, visit
from graphql.language.ast import TypeExtensionDefinition
from .types_util import SchemaData, SchemaError


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


def get_schema_data(ast):
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

