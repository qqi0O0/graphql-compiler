from graphql import build_ast_schema
from graphql.language import ast as ast_types
from graphql.language.visitor import visit, Visitor, REMOVE

from .utils import SchemaStructureError, get_query_type_name, get_scalar_names


def restrict_schema(schema_ast, types_to_keep):
    """Return new AST containing only a subset of types.

    In addition to all types named in types_to_keep, the query type will also be kept. All user
    defined scalars and enums will be kept.
    All property fields will be kept, and only vertex fields that go to kept types will be
    kept.

    Args:
        schema_ast: Document, representing the schema we're using to create a new schema with
                    fewer types. It is not modified by this function
        types_to_keep: Set[str], the set of names of types that we want to keep in the output
                       schema

    Returns:
        Document, representing the schema that is derived from the input schema AST, but only
        keeping a subset of types and a subset of vertex fields. The query type is additionally
        also always kept

    Raises:
        SchemaStructureError if types_to_keep is inconsistent, in that some union type is included
        but not all of its subtypes are included, or if some type has no remaining fields, or if
        for some other reason the resulting schema AST cannot be made into a valid schema
    """
    schema = build_ast_schema(schema_ast)
    query_type_name = get_query_type_name(schema)
    scalar_names = get_scalar_names(schema)
    visitor = RestrictSchemaVisitor(
        types_to_keep, query_type_name, scalar_names
    )
    restricted_schema = visit(schema_ast, visitor)
    # The restricted schema may contain types with no fields left
    try:
        build_ast_schema(schema_ast)
    except Exception as e:  # Can't be more specific, build_ast_schema throws Exceptions
        raise SchemaStructureError(u'The resulting schema is invalid. Message: {}'.format(e))

    # Note that it is possible for some types in the restricted schema to be unreachable
    return restricted_schema


class RestrictSchemaVisitor(Visitor):
    """Remove types that are not explicitly kept, and fields go these types."""
    normal_definition_types = frozenset({
        'InterfaceTypeDefinition',
        'ObjectTypeDefinition',
    })
    union_definition_type = 'UnionTypeDefinition',
    field_definition_type = 'FieldDefinition'

    def __init__(self, types_to_keep, query_type, scalars):
        """Create a visitor for removing types and fields.

        Args:
            types_to_keep: Set[str], the set of names of types that we want to keep in the schema
            query_type: str, name of the query type in the schema. The query type is always kept
            scalars: str, names of scalar types, both builtin and user defined. Used to identify
                     property fields, as such fields are kept
        """
        self.types_to_keep = types_to_keep
        self.query_type = query_type
        self.scalars = scalars

    def enter(self, node, *args):
        """
        """
        node_type = type(node).__name__
        if node_type in self.normal_definition_types:
            node_name = node.name.value
            if node_name == self.query_type:  # Query type, don't remove even if unlisted
                return None
            elif node_name in self.types_to_keep:
                return None
            else:
                return REMOVE
        elif node_type == self.union_definition_type:
            node_name = node.name.value
            if node_name in self.type_to_keep:
                # Check that all subtypes of the union are also kept
                union_sub_types = [sub_type.name.value for subtype in node.types]
                if any(
                    union_sub_type not in self.types_to_keep
                    for union_sub_type in union_sub_types
                ):
                    raise SchemaStructureError(
                        u'Not all of the subtypes, {}, of the union type "{}" are in the set of '
                        u'types to keep.'.format(union_sub_types, node_name)
                    )
                return None
            else:
                return REMOVE
        elif node_type == self.field_definition_type:
            type_of_field = node.type
            while not isinstance(type_of_field, ast_types.NamedType):
                type_of_field = type_of_field.type
            type_name_of_field = type_of_field.name.value
            if type_name_of_field in self.types_to_keep or type_name_of_field in self.scalars:
                return None
            else:
                return REMOVE
        else:
            return None
