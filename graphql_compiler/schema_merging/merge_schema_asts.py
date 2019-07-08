# Copyright 2019-present Kensho Technologies, LLC.
import copy

from graphql.language import ast

from .utils import get_schema_data


def merge_schema_asts(ast1, ast2):
    """Merge two schema asts.

    Given two schema asts, construct a new schema ast that contains the union of the types,
    scalars, directives of the input schema asts, whose query root fields is the union of the
    query root fields of the input schema asts. The two asts must not have name conflicts among
    its types and root fields.

    The two asts do not need to be valid on their own. For example, ast2 may refer to a scalar
    type that is not defined in ast2.

    Args:
        ast1, ast2: Documents representing schemaa; not modified by the function

    Return:
        Document that merged ast1 and ast2
    """
    # TODO: change this to either be a helper function that doesn't do any of the validity checks
    # and just exists as a small part of the merge_schemas file, or make it a standalone thing
    # that takes care of the deduplication
    # NOTE: it's pretty hard to check that these ASTs are of the right format without using a
    # try catch block with build_ast_schema
    assert isinstance(ast1, ast.Document)
    assert isinstance(ast2, ast.Document)

    schema_data1 = get_schema_data(ast1)
    schema_data2 = get_schema_data(ast2)

    merged_ast = copy.deepcopy(ast1)
    new_ast = copy.deepcopy(ast2)

    # TODO: assert scalar sets are disjoint
    # TODO: assert directive sets are disjoint
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
    if merged_query_type is None:
        raise Exception('Query type not found.')
    if new_root_fields is None:
        raise Exception('Root fields not found.')
    for new_root_field in new_root_fields:
        merged_query_type.fields.append(new_root_field)

    return merged_ast

# TODO: more rigorous input correctness check
# TODO: tests
