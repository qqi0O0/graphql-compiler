# Copyright 2019-present Kensho Technologies, LLC.
from collections import OrderedDict
from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast

from graphql_compiler.schema_transformation.merge_schemas import merge_schemas
from graphql_compiler.schema_transformation.rename_schema import rename_schema
from graphql_compiler.schema_transformation.utils import (
    SchemaNameConflictError, SchemaStructureError
)

from .input_schema_strings import InputSchemaStrings as ISS


class PrefixDict(object):
    def __init__(self, prefix):
        self.prefix = prefix

    def get(self, key, default=None):
        return self.prefix + key

    def __contains__(self, key):
        return True


class TestMergeSchemas(unittest.TestCase):
    def test_no_rename_basic_merge(self):
        merged_schema = merge_schemas(
            OrderedDict({
                'basic': parse(ISS.basic_schema),
                'enum': parse(ISS.enum_schema)
            })
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
            }

            type Human {
              id: String
            }

            type Droid {
              height: Height
            }

            enum Height {
              TALL
              SHORT
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))
        self.assertEqual({'Droid': 'enum', 'Height': 'enum', 'Human': 'basic'},
                         merged_schema.name_id_map)

    def test_rename_basic_merge(self):
        merged_schema = merge_schemas(
            OrderedDict({
                'first': rename_schema(parse(ISS.basic_schema), PrefixDict('First')).schema_ast,
                'second': rename_schema(parse(ISS.basic_schema), PrefixDict('Second')).schema_ast
            })
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              FirstHuman: FirstHuman
              SecondHuman: SecondHuman
            }

            type FirstHuman {
              id: String
            }

            type SecondHuman {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))
        self.assertEqual({'FirstHuman': 'first', 'SecondHuman': 'second'},
                         merged_schema.name_id_map)

    def test_multiple_merge(self):
        merged_schema = merge_schemas(
            OrderedDict({
                'first': parse(ISS.basic_schema),
                'second': parse(ISS.enum_schema),
                'third': rename_schema(parse(ISS.interface_schema), {'Human': 'Human2'}).schema_ast,
                'fourth': rename_schema(parse(ISS.scalar_schema), {'Human': 'Human3'}).schema_ast
            })
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
              Character: Character
              Human2: Human2
              Human3: Human3
            }

            type Human {
              id: String
            }

            type Droid {
              height: Height
            }

            enum Height {
              TALL
              SHORT
            }

            interface Character {
              id: String
            }

            type Human2 implements Character {
              id: String
            }

            type Human3 {
              birthday: Date
            }

            scalar Date
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_diff_query_type_name_merge(self):
        diff_query_type_schema = dedent('''\
            schema {
              query: RandomRootSchemaQueryName
            }

            type Droid {
              id: String
            }

            type RandomRootSchemaQueryName {
              Droid: Droid
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict({
                'first': parse(ISS.basic_schema),
                'second': parse(diff_query_type_schema)
            })
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
            }

            type Human {
              id: String
            }

            type Droid {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_invalid_input_schema(self):
        with self.assertRaises(SchemaStructureError):
            merge_schemas(
                OrderedDict({
                    'invalid': parse(ISS.invalid_schema)
                })
            )

    def test_type_conflict_merge(self):
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict({
                    'first': parse(ISS.basic_schema),
                    'second': parse(ISS.basic_schema)
                })
            )

    def test_interface_type_conflict_merge(self):
        interface_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            interface Human {
              id: String
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict({
                    'basic': parse(ISS.basic_schema),
                    'bad': parse(interface_conflict_schema)
                })
            )

    def test_enum_type_conflict_merge(self):
        enum_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            enum Human {
              CHILD
              ADULT
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict({
                    'basic': parse(ISS.basic_schema),
                    'bad': parse(enum_conflict_schema)
                })
            )

    def test_enum_interface_conflict_merge(self):
        enum_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            enum Character {
              FICTIONAL
              REAL
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict({
                    'interface': parse(ISS.interface_schema),
                    'bad': parse(enum_conflict_schema)
                })
            )

    def test_type_scalar_conflict_merge(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            scalar Human
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict({
                    'basic': parse(ISS.basic_schema),
                    'bad': parse(scalar_conflict_schema)
                })
            )

    def test_interface_scalar_conflict_merge(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            scalar Character
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict({
                    'interface': parse(ISS.interface_schema),
                    'bad': parse(scalar_conflict_schema)
                })
            )

    def test_enum_scalar_conflict_merge(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            scalar Height
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict({
                    'enum': parse(ISS.enum_schema),
                    'bad': parse(scalar_conflict_schema)
                })
            )

    def test_dedup_scalars(self):
        extra_scalar_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            scalar Date

            scalar Decimal

            type Kid {
              height: Decimal
            }

            type SchemaQuery {
              Kid: Kid
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict({
                'first': rename_schema(parse(ISS.scalar_schema), PrefixDict('First')).schema_ast,
                'second': rename_schema(parse(extra_scalar_schema), PrefixDict('Second')).schema_ast
            })
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              FirstHuman: FirstHuman
              SecondKid: SecondKid
            }

            type FirstHuman {
              birthday: Date
            }

            scalar Date

            scalar Decimal

            type SecondKid {
              height: Decimal
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))
        self.assertEqual({'FirstHuman': 'first', 'SecondKid': 'second'},
                         merged_schema.name_id_map)

    def test_dedup_same_directives(self):
        extra_directive_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

            directive @output(out_name: String!) on FIELD

            type Kid {
              id: String
            }

            type SchemaQuery {
              Kid: Kid
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict({
                'first': parse(ISS.directive_schema),
                'second': parse(extra_directive_schema)
            })
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
              Kid: Kid
            }

            type Human {
              id: String
            }

            type Droid {
              id: String
              friend: Human @stitch(source_field: "id", sink_field: "id")
            }

            directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

            directive @output(out_name: String!) on FIELD

            type Kid {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))
        self.assertEqual({'Human': 'first', 'Droid': 'first', 'Kid': 'second'},
                         merged_schema.name_id_map)

    def test_dedup_clashing_directives(self):
        extra_directive_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            directive @stitch(out_name: String!) on FIELD

            type Kid {
              id: String
            }

            type SchemaQuery {
              Kid: Kid
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict({
                    'first': parse(ISS.directive_schema),
                    'second': parse(extra_directive_schema)
                })
            )
