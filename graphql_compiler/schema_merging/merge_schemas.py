# Copyright 2019-present Kensho Technologies, LLC.
"""TODO:
Always add in the stitch directive as a special case for now
cross server edge descriptor
"""


from collections import namedtuple

from graphql import parse, build_ast_schema
from graphql.language import ast as ast_types
import six

from .utils import (
    SchemaNameConflictError, SchemaStructureError, get_query_type_name,
    _check_ast_schema_valid
)


MergedSchema = namedtuple(
    'MergedSchema', [
        'schema_ast',  # Document, ast representing the merged schema
        'name_id_map',  # Dict[str, str], type name to id of the schema the type is from
    ]
)


def basic_schema_ast(query_type):
    """Create a basic ast Document representing a nearly blank schema.

    ast contains a single query type, whose name is the input string. The query type is
    guaranteed to be the second entry of Document definitions, after the schema definition.
    The query type has no fields.

    Args:
        query_type: str, name of the query type for the schema

    Returns:
        Document, representing a nearly blank schema
    """
    return ast_types.Document(
        definitions=[
            ast_types.SchemaDefinition(
                operation_types=[
                    ast_types.OperationTypeDefinition(
                        operation='query',
                        type=ast_types.NamedType(
                            name=ast_types.Name(value=query_type)
                        )
                    )
                ]
            ),
            ast_types.ObjectTypeDefinition(
                name=ast_types.Name(value=query_type),
                fields=[]
            )
        ]
    )


def merge_schemas(schemas_dict):
    """Check that input schemas do not contain conflicting definitions, then merge.

    Merged schema will contain all type, interface, enum, scalar, and directive definitions
    from input schemas. Its root fields will be the union of all root fields from input
    schemas.

    Args:
        schemas_dict: OrderedDict where keys are schema_identifiers, and values are
                      strings describing schemas

    Returns:
        MergedSchema, a namedtuple that contains the ast of the merged schema, and the map
        from names of types/root fields to the id of the schema that they came from

    Raises:
        GraphQLSyntaxError if a input schema string cannot be parsed
        SchemaStructureError if the schema does not have the expected form; in particular, if
        the parsed ast does not represent a valid schema, if any root field does not have the
        same name as the type that it queries, if the schema contains type extensions or
        input object definitions, or if the schema contains mutations or subscriptions
        SchemaNameConflictError if there are conflicts between the names of
        types/interfaces/enums/scalars, or conflicts between the definition of directives
        with the same name
    """
    if len(schemas_dict) == 0:
        raise ValueError("Expected a nonzero number of schemas to merge.")

    query_type = 'RootSchemaQuery'
    # NOTE: currently, the query type will always be named RootSchemaQuery
    # could be changed so the user has an input, or by changed to always use the root query
    # name in the first schema in the input
    merged_schema_ast = basic_schema_ast(query_type)  # Document
    merged_definitions = merged_schema_ast.definitions  # List[Node]
    merged_root_fields = merged_definitions[1].fields  # List[FieldDefinition]

    name_id_map = {}  # Dict[str, str], name of type/interface/enum/union to schema id
    scalars = {'String', 'Int', 'Float', 'Boolean', 'ID'}  # Set[str], user defined + builtins
    directives = {}  # Dict[str, DirectiveDefinition]

    for schema_id, schema_string in six.iteritems(schemas_dict):
        # Parse and attempt to construct schema

        # May raise GraphQLSyntaxError
        cur_ast = parse(schema_string)

        try:
            cur_schema = build_ast_schema(cur_ast)
        except Exception as e:
            raise SchemaStructureError('Input is not a valid schema. Message: {}'.format(e))

        # Check additional structural requirements
        _check_ast_schema_valid(cur_ast, cur_schema)

        cur_query_type = get_query_type_name(cur_schema)

        # Merge cur_ast into merged_schema_ast
        # Concatenate new scalars, new directive, and all type definitions
        # Raise errors for conflicting scalars, directives, or types
        new_definitions = cur_ast.definitions  # List[Node]
        new_root_fields = None  # List[FieldDefinition]
        for new_definition in new_definitions:
            if isinstance(new_definition, ast_types.SchemaDefinition):
                continue

            new_name = new_definition.name.value

            if (
                isinstance(new_definition, ast_types.ObjectTypeDefinition) and
                new_name == cur_query_type
            ):  # root type definition
                new_root_fields = new_definition.fields  # List[FieldDefinition]

            elif isinstance(new_definition, ast_types.ScalarTypeDefinition):
                if new_name in scalars:  # existing scalar
                    print('existing scalar')
                    continue
                if new_name in name_id_map:  # new scalar clashing with existing type
                    raise SchemaNameConflictError(
                        'New scalar "{}" clashes with existing type.'.format(new_name)
                    )
                # new, valid scalar
                merged_definitions.append(new_definition)  # Add to ast
                scalars.add(new_name)

            elif isinstance(new_definition, ast_types.DirectiveDefinition):
                if new_name in directives:
                    # if definitions agree, continue
                    # TODO: check if directives have equality implemented
                    # else, raise error
                    pass
                # new directive
                merged_definitions.append(new_definition)  # Add to ast
                directives[new_name] = new_definition

            else:  # Generic type definition
                if new_name in scalars:
                    # TODO: change SchemaNameConflictError to SchemaNameConflictError
                    raise SchemaNameConflictError(
                        'New type "{}" clashes with existing scalar.'.format(type_name)
                    )
                if new_name in name_id_map:
                    raise SchemaNameConflictError(
                        'New type "{}" clashes with existing type.'.format(type_name)
                    )
                merged_definitions.append(new_definition)
                name_id_map[new_name] = schema_id

        # Concatenate all root fields
        # Given that names of root fields agree with their queried types, and that types were
        # merged without conflicts, root fields will also merge without conflicts and it is not
        # necessary to check for identical names
        if new_root_fields is None:
            raise AssertionError('Root fields unexpected not found.')

        merged_root_fields.extend(new_root_fields)

    return MergedSchema(schema_ast=merged_schema_ast, name_id_map=name_id_map)
