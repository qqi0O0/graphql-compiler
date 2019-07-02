from graphql.language.visitor import Visitor, visit
from graphql.language import ast
from graphql.language.ast import TypeExtensionDefinition
from .types_util import SchemaData, SchemaError


class RenameSchemaVisitor(Visitor):
    """Traverse a Document AST, editing the names of nodes."""
    def __init__(self, rename_func, query_type, scalar_types):
        self.rename_func = rename_func  # callable that takes string to string
        self.reverse_name_map = {}  # Dict[str, str], from new name to original name
        self.query_type = query_type
        self.scalar_types = scalar_types
        self.builtin_types = {'String', 'Int', 'Float', 'Boolean', 'ID'}

    def _rename_name_add_to_record(self, node):
        """Rename the value of the node, and add the name mapping to reverse_name_map.

        Don't rename if the type is the query type, a scalar type, or a built in type.

        Args:
            node: Name type Node
        """
        name_string = node.value

        if (
            name_string == self.query_type or
            name_string in self.scalar_types or
            name_string in self.builtin_types
        ):
            return

        new_name_string = self.rename_func(name_string)
        node.value = new_name_string
        if (
            new_name_string in self.reverse_name_map and
            self.reverse_name_map[new_name_string] != name_string
        ):
            raise SchemaError(
                '"{}" and "{}" are both renamed to "{}"'.format(
                    name_string, self.reverse_name_map[new_name_string], new_name_string
                )
            )
        if new_name_string in self.scalar_types:
            raise SchemaError(
                '"{}" was renamed to "{}", clashing with scalar "{}"'.format(
                    name_string, new_name_string, new_name_string
                )
            )
        if new_name_string in self.builtin_types:
            raise SchemaError(
                '"{}" was renamed to "{}", clashing with builtin "{}"'.format(
                    name_string, new_name_string, new_name_string
                )
            )

        self.reverse_name_map[new_name_string] = name_string

    # In order of QUERY_DOCUMENT_KEYS
    # returning False means skip branch

    def enter_Name(self, node, *args):
        pass

    def enter_Document(self, node, *args):
        pass

    def enter_OperationDefinition(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_VariableDefinition(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_Variable(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_SelectionSet(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_Field(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_Argument(self, node, *args):
        # argument of directive
        return False

    def enter_FragmentSpread(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_InlineFragment(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_FragmentDefinition(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_IntValue(self, node, *args):
        return False

    def enter_FloatValue(self, node, *args):
        return False

    def enter_StringValue(self, node, *args):
        return False

    def enter_BooleanValue(self, node, *args):
        return False

    def enter_EnumValue(self, node, *args):
        return False

    def enter_ListValue(self, node, *args):
        pass

    def enter_ObjectValue(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_ObjectField(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_Directive(self, node, *args):
        # TODO: behavior is not clear
        pass
        # raise AssertionError('Unimplemented')

    def enter_NamedType(self, node, *args):
        """Rename all named types that are not the query type, scalars, or builtins."""
        self._rename_name_add_to_record(node.name)

    def enter_ListType(self, node, *args):
        pass

    def enter_NonNullType(self, node, *args):
        pass

    def enter_SchemaDefinition(self, node, *args):
        pass

    def enter_OperationTypeDefinition(self, node, *args):
        return False

    def enter_ScalarTypeDefinition(self, node, *args):
        pass

    def enter_ObjectTypeDefinition(self, node, *args):
        # NamedType takes care of interfaces, FieldDefinition takes care of fields
        # NOTE: directives
        self._rename_name_add_to_record(node.name)

    def enter_FieldDefinition(self, node, *args):
        # No rename name, InputValueDefinition takes care of arguments, NamedType cares care of type
        # NOTE: directives
        pass

    def enter_InputValueDefinition(self, node, *args):
        # No rename name, NamedType takes care of type, no rename default_value
        # NOTE: directives
        pass

    def enter_InterfaceTypeDefinition(self, node, *args):
        # FieldDefinition takes care of fields
        # NOTE: directives
        self._rename_name_add_to_record(node.name)

    def enter_UnionTypeDefinition(self, node, *args):
        # NamedType takes care of types
        # NOTE: directives
        self._rename_name_add_to_record(node.name)

    def enter_EnumTypeDefinition(self, node, *args):
        # EnumValueDefinition takes care of values
        # NOTE: directives
        self._rename_name_add_to_record(node.name)

    def enter_EnumValueDefinition(self, node, *args):
        pass

    def enter_InputObjectTypeDefinition(self, node, *args):
        raise AssertionError('Unimplemented')

    def enter_TypeExtensionDefinition(self, node, *args):
        raise SchemaError('Extension definition not allowed')

    def enter_directive_definition(self, node, *args):
        pass


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

#    def enter_InterfaceTypeDefinition(self, node, *args):
#        self.schema_data.types.add(node.name.value)

#    def enter_ObjectTypeDefinition(self, node, *args):
#        self.schema_data.types.add(node.name.value)

#    def enter_UnionTypeDefinition(self, node, *args):
#        self.schema_data.types.add(node.name.value)

#    def enter_EnumTypeDefinition(self, node, *args):
#        self.schema_data.types.add(node.name.value)

    def enter_ScalarTypeDefinition(self, node, *args):
        self.schema_data.scalars.add(node.name.value)

    def enter_DirectiveDefinition(self, node, *args):
        # NOTE: currently we don't check if the definitions of the directives agree
        # any directive that comes after one of the same one is simply erased, even if it
        # has a different definition
        # In fact, only the directives of the first schema are kept, due to the behavior of
        # extend_schema
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


class DemangleQueryVisitor(Visitor):
    def __init__(self, reverse_name_id_map, reverse_root_field_id_map, schema_identifier):
        pass


