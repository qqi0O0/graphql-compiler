# Copyright 2019-present Kensho Technologies, LLC
from collections import OrderedDict

from graphql import parse
from graphql_compiler.schema_transformation.merge_schemas import (
    CrossSchemaEdgeDescriptor, FieldReference, merge_schemas
)


schema1 = '''
schema {
  query: SchemaQuery
}

type Human {
  name: String
  friend: Human
  id: String
}

type SchemaQuery {
  Human: Human
}
'''

schema2 = '''
schema {
  query: SchemaQuery
}

type Person {
  age: Int
  enemy: Person
  identifier: String
}

type SchemaQuery {
  Person: Person
}
'''

basic_merged_schema = merge_schemas(
    OrderedDict([
        ('first', parse(schema1)),
        ('second', parse(schema2)),
    ]),
    [
        CrossSchemaEdgeDescriptor(
            edge_name='Human_Person',
            outbound_field_reference=FieldReference(
                schema_id='first',
                type_name='Human',
                field_name='id',
            ),
            inbound_field_reference=FieldReference(
                schema_id='second',
                type_name='Person',
                field_name='identifier'
            ),
            out_edge_only=False,
        ),
    ],
)
