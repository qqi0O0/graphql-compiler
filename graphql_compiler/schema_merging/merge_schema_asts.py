import copy
from graphql.language import ast
from .visitors import get_schema_data

def merge_schema_asts(ast1, ast2):
    """Merge two schema asts.

    Given two schema asts, construct a new schema ast that contains the union of the types,
    scalars, directives of the input schema asts, whose query root fields is the union of the
    query root fields of the input schema asts. The two asts must not have name conflicts among
    its types and root fields.

    Args:
        ast1, ast2: Documents representing schemaa; not modified by the function

    Return:
        Document that merged ast1 and ast2
    """
    # NOTE: it's pretty hard to check that these ASTs are of the right format without using a
    # try catch block with build_ast_schema
    assert isinstance(ast1, ast.Document)
    assert isinstance(ast2, ast.Document)

    merged_ast = copy.deepcopy(ast1)
    new_ast = copy.deepcopy(ast2)

    schema_data1 = get_schema_data(merged_ast)
    schema_data2 = get_schema_data(new_ast)

    assert schema_data1.scalars.isdisjoint(schema_data2.scalars)
    assert schema_data1.directives.isdisjoint(schema_data2.directives)
    # TODO: assert root fields are disjoint
    # TODO: assert types are disjoint

    # Merge type definitions
    new_definitions = new_ast.definitions  # type: List[Node]
    new_root_fields = None
    for new_definition in new_definitions:
        if isinstance(new_definition, ast.SchemaDefinition):
            continue
        elif (
            isinstance(new_definition, ast.ObjectTypeDefinition) and
            new_definition.name.value == schema_data2.query_type
        ):  # query type
            new_root_fields = new_definition.fields  # type: List[FieldDefinition]
        else:  # general type definition
            merged_ast.definitions.append(new_definition)

    # Merge root fields
    merged_query_type = None
    for definition in merged_ast.definitions:
        if (
            isinstance(definition, ast.ObjectTypeDefinition) and
            definition.name.value == schema_data1.query_type
        ):
            merged_query_type = definition
            break
    if merged_query_type == None:
        raise Exception('Query type not found.')
    if new_root_fields == None:
        raise Exception('Root fields not found.')
    for new_root_field in new_root_fields:
        merged_query_type.fields.append(new_root_field)

    return merged_ast

# TODO: more rigorous input correctness check
# TODO: tests
