# Copyright 2019-present Kensho Technologies, LLC
from collections import OrderedDict

from graphql import parse
from graphql_compiler.schema_transformation.merge_schemas import (
    CrossSchemaEdgeDescriptor, FieldReference, merge_schemas
)
from ..test_helpers import SCHEMA_TEXT


additional_schema = '''
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
        ('first', parse(SCHEMA_TEXT)),
        ('second', parse(additional_schema)),
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
