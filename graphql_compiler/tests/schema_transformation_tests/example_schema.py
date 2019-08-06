# Copyright 2019-present Kensho Technologies, LLC
from collections import OrderedDict
import six

from graphql import parse, build_ast_schema
from graphql_compiler.schema_transformation.merge_schemas import (
    CrossSchemaEdgeDescriptor, FieldReference, merge_schemas
)
from graphql_compiler.schema_transformation.rename_schema import rename_schema

from ..test_helpers import SCHEMA_TEXT


basic_schema = parse(SCHEMA_TEXT)


basic_renamed_schema = rename_schema(
    basic_schema, {'Animal': 'NewAnimal', 'Entity': 'NewEntity', 'BirthEvent': 'NewBirthEvent'}
)


basic_additional_schema = '''
schema {
  query: SchemaQuery
}

type Creature {
  creature_name: String
  age: Int
  out_Creature_ParentOf: [Creature]
}

type SchemaQuery {
  Creature: Creature
}
'''


basic_merged_schema = merge_schemas(
    OrderedDict([
        ('first', basic_schema),
        ('second', parse(basic_additional_schema)),
    ]),
    [
        CrossSchemaEdgeDescriptor(
            edge_name='Animal_Creature',
            outbound_field_reference=FieldReference(
                schema_id='first',
                type_name='Animal',
                field_name='name',
            ),
            inbound_field_reference=FieldReference(
                schema_id='second',
                type_name='Creature',
                field_name='creature_name'
            ),
            out_edge_only=False,
        ),
    ],
)


interface_additional_schema = '''
schema {
  query: SchemaQuery
}

interface Creature {
  creature_name: String
  age: Int
}

type Cat implements Creature {
  creature_name: String
  age: Int
}

type SchemaQuery {
  Creature: Creature
  Cat: Cat
}
'''


interface_merged_schema = merge_schemas(
    OrderedDict([
        ('first', basic_schema),
        ('second', parse(interface_additional_schema)),
    ]),
    [
        CrossSchemaEdgeDescriptor(
            edge_name='Animal_Creature',
            outbound_field_reference=FieldReference(
                schema_id='first',
                type_name='Animal',
                field_name='name',
            ),
            inbound_field_reference=FieldReference(
                schema_id='second',
                type_name='Creature',
                field_name='creature_name'
            ),
            out_edge_only=False,
        ),
    ],
)


def get_type_equivalence_hints(schema_id_to_ast, type_equivalence_hints_names):
    """Get type_equivalence_hints for input into merge_schemas.

    Args:
        schema_id_to_ast: Dict[str, Document]
        type_equivalence_hints_names: Dict[str, str]

    Returns:
        Dict[GraphQLObjectType, GraphQLUnionType]
    """
    name_to_type = {}
    for ast in six.itervalues(schema_id_to_ast):
        schema = build_ast_schema(ast)
        name_to_type.update(schema.get_type_map())
    type_equivalence_hints = {}
    for object_type_name, union_type_name in six.iteritems(type_equivalence_hints_names):
        object_type = name_to_type[object_type_name]
        union_type = name_to_type[union_type_name]
        type_equivalence_hints[object_type] = union_type
    return type_equivalence_hints


union_additional_schema = '''
schema {
  query: SchemaQuery
}

type Creature {
  creature_name: String
  age: Int
}

type Cat {
  creature_name: String
  age: Int
}

union CreatureOrCat = Creature | Cat

type SchemaQuery {
  Creature: Creature
  Cat: Cat
}
'''


union_schema_id_to_ast = OrderedDict([
    ('first', basic_schema),
    ('second', parse(union_additional_schema)),
])


union_merged_schema = merge_schemas(
    union_schema_id_to_ast,
    [
        CrossSchemaEdgeDescriptor(
            edge_name='Animal_Creature',
            outbound_field_reference=FieldReference(
                schema_id='first',
                type_name='Animal',
                field_name='name',
            ),
            inbound_field_reference=FieldReference(
                schema_id='second',
                type_name='Creature',
                field_name='creature_name'
            ),
            out_edge_only=False,
        ),
    ],
    get_type_equivalence_hints(union_schema_id_to_ast, {'Creature': 'CreatureOrCat'})
)
