# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple

from graphql import build_ast_schema, parse
from graphql.language.visitor import Visitor, visit
from graphql.type.definition import GraphQLScalarType

from .utils import SchemaError


RenamedSchema = namedtuple(
    'RenamedSchema', (
        'schema_ast',  # type: Document, ast representing the renamed schema
        'reverse_name_map',  # type: Dict[str, str], renamed type name to original type name
        'reverse_root_field_map'  # type: Dict[str, str], renamed field name to original field name
    )
)


def rename_schema(schema_string, rename_dict):
    """Create a RenamedSchema, where types and query root fields are renamed using rename_dict.

    Any type, interface, enum, or root field (fields of the root type/query type) whose name
    appears in rename_dict will be renamed to the corresponding value. Any such names that do not
    appear in rename_dict will be unchanged. Scalars, directives, enum values, and fields not
    belonging to the root type will never be renamed.

    Args:
        schema_string: string describing a valid schema that does not contain extensions,
                       input object definitions, mutations, or subscriptions
        rename_dict: Dict[str, str], mapping original type/field names to renamed type/field names.
                     Type or root field names that do not appear in the dict will be unchanged.
                     Any dict-like object that implements get(key, default_value) may also be used.

    Returns:
        RenamedSchema, a namedtuple that contains the ast of the renamed schema, the map of renamed
        type names to original type names, and the map of renamed root field (fields of the root
        type/query type) names to original root field names.

    Raises:
        SchemaError if there are conflicts between the renamed types or root fields or if input
        schema_string does not represent a valid input schema
    """
    # Check that the input string is a parseable and valid schema.
    try:
        ast = parse(schema_string)
        schema = build_ast_schema(ast)  # Check that the ast can be built into a valid schema
    except Exception as e:  # Can't be more specific -- see graphql/utils/build_ast_schema.py
        raise SchemaError(u'Input schema does not define a valid schema. Message: {}'.format(e))

    query_type = schema.get_query_type().name
    type_map = schema.get_type_map()
    # Set of scalars used in the schema, including any used builtins but excluding unused builtins
    # NOTE: this is different from the set that get_schema_data returns, since it contains some
    # subset of builtin scalars. The inclusion or exclusion of these builtins doesn't affect the
    # renaming of types since builtins are ignored as well, but it does feel more complex and
    # confusing
    scalars = {
        type_name for type_name in type_map if isinstance(type_map[type_name], GraphQLScalarType)
    }

    # Rename types, interfaces, enums
    reverse_name_map = _rename_types(ast, rename_dict, query_type, scalars)

    # Rename root fields
    reverse_root_field_map = _rename_root_fields(ast, rename_dict, query_type)

    return RenamedSchema(schema_ast=ast, reverse_name_map=reverse_name_map,
                         reverse_root_field_map=reverse_root_field_map)


def _rename_types(ast, rename_dict, query_type, scalars):
    """Rename types, enums, interfaces using rename_dict.

    The query type will not be renamed. Scalar types, field names, enum values will not be renamed.

    ast will be modified as a result.

    Args:
        ast: Document, the schema ast that we modify
        rename_dict: Dict[str, str], mapping original type/interface/enum name to renamed name. If
                     a name does not appear in the dict, it will be unchanged
        query_type: string, name of the query type, e.g. 'RootSchemaQuery'
        scalars: set of strings, the set of user defined scalars

    Returns:
        Dict[str, str], the renamed type name to original type name map

    Raises:
        SchemaError if the rename causes name conflicts
    """
    visitor = RenameSchemaTypesVisitor(rename_dict, query_type, scalars)
    visit(ast, visitor)

    return visitor.reverse_name_map


def _rename_root_fields(ast, rename_dict, query_type):
    """Rename root fields, aka fields of the query type.

    ast will be modified as a result.

    Args:
        ast: Document, the schema ast that we modify
        rename_dict: Dict[str, str], mapping original root field name to renamed name. If a name
                     does not appear in the dict, it will be unchanged
        query_type: string, name of the query type, e.g. 'RootSchemaQuery'

    Returns:
        Dict[str, str], the renamed root field name to original root field name map

    Raises:
        SchemaError if rename causes root field name conflicts
    """
    visitor = RenameRootFieldsVisitor(rename_dict, query_type)
    visit(ast, visitor)

    return visitor.reverse_field_map


class RenameSchemaTypesVisitor(Visitor):
    """Traverse a Document AST, editing the names of nodes."""

    noop_types = frozenset({
        'Argument',
        'BooleanValue',
        'Directive',
        'DirectiveDefinition',
        'Document',
        'EnumValue',
        'EnumValueDefinition',
        'FieldDefinition',
        'FloatValue',
        'InputValueDefinition',
        'IntValue',
        'ListValue',
        'ListType',
        'Name',
        'NonNullType',
        'OperationTypeDefinition',
        'ScalarTypeDefinition',
        'SchemaDefinition',
        'StringValue',
    })
    rename_types = frozenset({
        'EnumTypeDefinition',
        'InterfaceTypeDefinition',
        'NamedType',
        'ObjectTypeDefinition',
        'UnionTypeDefinition',
    })
    unexpected_types = frozenset({
        'Field',
        'FragmentDefinition',
        'FragmentSpread',
        'InlineFragment',
        'ObjectField',
        'ObjectValue',
        'OperationDefinition',
        'SelectionSet',
        'Variable',
        'VariableDefinition',
    })
    disallowed_types = frozenset({
        'InputObjectTypeDefinition',
        'TypeExtensionDefinition',
    })

    def __init__(self, rename_dict, query_type, scalar_types):
        self.rename_dict = rename_dict
        # Dict[str, str], from original type name to renamed type name; any name not in the dict
        # will be unchanged
        self.reverse_name_map = {}  # Dict[str, str], from renamed type name to original type name
        self.query_type = query_type  # str
        # TODO: rename scalar_types to user_defined_scalars in many places?
        self.scalar_types = frozenset(scalar_types)
        self.builtin_types = frozenset({'String', 'Int', 'Float', 'Boolean', 'ID'})

    def _rename_name_add_to_record(self, node):
        """Rename the value of the node, and add the name mapping to reverse_name_map.

        Don't rename if the type is the query type, a scalar type, or a builtin type.

        Modifies node and potentially modifies reverse_name_map.

        Args:
            node: type Name (see graphql/language/ast)

        Raises:
            SchemaError if the newly renamed node causes name conflicts with existing types,
            scalars, or builtin types
        """
        name_string = node.value

        if (
            name_string == self.query_type or
            name_string in self.scalar_types or
            name_string in self.builtin_types
        ):
            return

        new_name_string = self.rename_dict.get(name_string, name_string)
        # Defaults to original name string if not found in rename_dict

        if (
            new_name_string in self.reverse_name_map and
            self.reverse_name_map[new_name_string] != name_string
        ):
            raise SchemaError(
                u'"{}" and "{}" are both renamed to "{}"'.format(
                    name_string, self.reverse_name_map[new_name_string], new_name_string
                )
            )
        if new_name_string in self.scalar_types:
            raise SchemaError(
                u'"{}" was renamed to "{}", clashing with scalar "{}"'.format(
                    name_string, new_name_string, new_name_string
                )
            )
        if new_name_string in self.builtin_types:
            raise SchemaError(
                u'"{}" was renamed to "{}", clashing with builtin "{}"'.format(
                    name_string, new_name_string, new_name_string
                )
            )

        node.value = new_name_string
        self.reverse_name_map[new_name_string] = name_string

    def enter(self, node, key, parent, path, ancestors):
        """Upon entering a node, operate depending on node type."""
        node_type = type(node).__name__
        if node_type in self.noop_types:
            # Do nothing, continue traversal
            return None
        elif node_type in self.rename_types:
            # Rename and put into record the name attribute of current node; continue traversal
            self._rename_name_add_to_record(node.name)
        elif node_type in self.unexpected_types:
            # Node type unexpected in schema definition, raise error
            raise SchemaError(u'Node type "{}" unexpected in schema AST'.format(node_type))
        elif node_type in self.disallowed_types:
            # Node type possible in schema definition but disallowed, raise error
            raise SchemaError(u'Node type "{}" not allowed'.format(node_type))
        else:
            # All Node types should've been taken care of, this line should never be reached
            raise AssertionError(u'Missed type: "{}"'.format(node_type))


class RenameRootFieldsVisitor(Visitor):
    def __init__(self, rename_dict, query_type):
        self.in_query_type = False
        self.rename_dict = rename_dict
        # Dict[str, str], from original field name to renamed field name; any name not in the dict
        # will be unchanged
        self.reverse_field_map = {}  # Dict[str, str], renamed field name to original field name
        self.query_type = query_type

    def enter_ObjectTypeDefinition(self, node, *args):
        """If entering query type, set flag to True."""
        if node.name.value == self.query_type:
            self.in_query_type = True

    def leave_ObjectTypeDefinition(self, node, key, parent, path, ancestors):
        """If leaving query type, set flag to False."""
        if node.name.value == self.query_type:
            self.in_query_type = False

    def enter_FieldDefinition(self, node, *args):
        """If entering field under query type, rename and add to reverse map."""
        if self.in_query_type:
            field_name = node.name.value
            new_field_name = self.rename_dict.get(field_name, field_name)
            # Defaults to original field name if not found in rename_dict

            if (
                new_field_name in self.reverse_field_map and
                self.reverse_field_map[new_field_name] != field_name
            ):
                raise SchemaError(
                    u'"{}" and "{}" are both renamed to "{}"'.format(
                        field_name, self.reverse_field_map[new_field_name], new_field_name
                    )
                )

            node.name.value = new_field_name
            self.reverse_field_map[new_field_name] = field_name
