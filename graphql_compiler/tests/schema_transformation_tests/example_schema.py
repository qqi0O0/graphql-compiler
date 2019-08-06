# Copyright 2019-present Kensho Technologies, LLC
from collections import OrderedDict

from graphql import parse
from graphql_compiler.schema_transformation.merge_schemas import (
    CrossSchemaEdgeDescriptor, FieldReference, merge_schemas
)
from graphql_compiler.schema_transformation.rename_schema import rename_schema
from ..test_helpers import SCHEMA_TEXT


basic_schema = parse(SCHEMA_TEXT)


basic_renamed_schema = rename_schema(
    basic_schema, {'Animal': 'NewAnimal', 'Entity': 'NewEntity'}
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
