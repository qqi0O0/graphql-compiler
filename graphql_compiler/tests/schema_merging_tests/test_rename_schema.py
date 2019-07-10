# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql.language.printer import print_ast
from graphql.language.visitor_meta import QUERY_DOCUMENT_KEYS

from graphql_compiler.schema_merging.rename_schema import RenameSchemaTypesVisitor, rename_schema
from graphql_compiler.schema_merging.utils import SchemaRenameConflictError, SchemaStructureError

from .input_schema_strings import InputSchemaStrings as ISS


class TestRenameSchema(unittest.TestCase):
    def test_rename_visitor_type_coverage(self):
        """Check that all types are covered without overlap."""
        all_types = set(ast_type.__name__ for ast_type in QUERY_DOCUMENT_KEYS)
        type_sets = [RenameSchemaTypesVisitor.noop_types,
                     RenameSchemaTypesVisitor.rename_types,
                     RenameSchemaTypesVisitor.unexpected_types,
                     RenameSchemaTypesVisitor.disallowed_types]
        type_sets_union = set()
        for type_set in type_sets:
            self.assertTrue(type_sets_union.isdisjoint(type_set))
            type_sets_union.update(type_set)
        self.assertEqual(all_types, type_sets_union)

    def test_no_rename(self):
        renamed_schema = rename_schema(ISS.basic_schema, {})

        self.assertEqual(ISS.basic_schema, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'Human': 'Human'}, renamed_schema.reverse_name_map)

    def test_basic_rename(self):
        renamed_schema = rename_schema(ISS.basic_schema, {'Human': 'NewHuman'})
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewHuman {
              id: String
            }

            type SchemaQuery {
              NewHuman: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewHuman': 'Human'}, renamed_schema.reverse_name_map)

    def test_enum_rename(self):
        renamed_schema = rename_schema(ISS.enum_schema,
                                       {'Droid': 'NewDroid', 'Height': 'NewHeight'})
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewDroid {
              height: NewHeight
            }

            type SchemaQuery {
              NewDroid: NewDroid
            }

            enum NewHeight {
              TALL
              SHORT
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewDroid': 'Droid', 'NewHeight': 'Height'},
                         renamed_schema.reverse_name_map)

    def test_interface_rename(self):
        renamed_schema = rename_schema(ISS.interface_schema,
                                       {'Human': 'NewHuman', 'Character': 'NewCharacter'})
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            interface NewCharacter {
              id: String
            }

            type NewHuman implements NewCharacter {
              id: String
            }

            type SchemaQuery {
              NewCharacter: NewCharacter
              NewHuman: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewHuman': 'Human', 'NewCharacter': 'Character'},
                         renamed_schema.reverse_name_map)

    def test_interfaces_rename(self):
        renamed_schema = rename_schema(
            ISS.interfaces_schema, {
                'Human': 'NewHuman', 'Character': 'NewCharacter', 'Creature': 'Creature'
            }
        )
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            interface NewCharacter {
              id: String
            }

            interface Creature {
              age: Int
            }

            type NewHuman implements NewCharacter, Creature {
              id: String
              age: Int
            }

            type SchemaQuery {
              NewCharacter: NewCharacter
              Creature: Creature
              NewHuman: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewHuman': 'Human', 'NewCharacter': 'Character', 'Creature': 'Creature'},
                         renamed_schema.reverse_name_map)

    def test_scalar_rename(self):
        renamed_schema = rename_schema(
            ISS.scalar_schema, {
                'Human': 'NewHuman', 'Date': 'NewDate', 'String': 'NewString'
            }
        )
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewHuman {
              birthday: Date
            }

            scalar Date

            type SchemaQuery {
              NewHuman: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewHuman': 'Human'}, renamed_schema.reverse_name_map)

    def test_union_rename(self):
        renamed_schema = rename_schema(ISS.union_schema,
                                       {'HumanOrDroid': 'NewHumanOrDroid', 'Droid': 'NewDroid'})
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type NewDroid {
              id: String
            }

            union NewHumanOrDroid = Human | NewDroid

            type SchemaQuery {
              Human: Human
              NewDroid: NewDroid
              NewHumanOrDroid: NewHumanOrDroid
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewDroid': 'Droid', 'NewHumanOrDroid': 'HumanOrDroid', 'Human': 'Human'},
                         renamed_schema.reverse_name_map)

    def test_list_rename(self):
        renamed_schema = rename_schema(ISS.list_schema,
                                       {'Droid': 'NewDroid', 'Character': 'NewCharacter',
                                        'Height': 'NewHeight', 'Date': 'NewDate',
                                        'id': 'NewId', 'String': 'NewString'})
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewDroid implements NewCharacter {
              id: String
              heights: [NewHeight]
              dates: [Date]
              friends: [NewDroid]
              enemies: [NewCharacter]
            }

            type SchemaQuery {
              NewDroid: [NewDroid]
            }

            scalar Date

            interface NewCharacter {
              id: String
            }

            enum NewHeight {
              TALL
              SHORT
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewCharacter': 'Character', 'NewDroid': 'Droid',
                          'NewHeight': 'Height'},
                         renamed_schema.reverse_name_map)

    def test_non_null_rename(self):
        renamed_schema = rename_schema(ISS.non_null_schema, {'Human': 'NewHuman'})
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewHuman {
              id: String!
              friend: NewHuman!
            }

            type SchemaQuery {
              NewHuman: NewHuman!
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewHuman': 'Human'}, renamed_schema.reverse_name_map)

    def test_directive_rename(self):
        renamed_schema = rename_schema(
            ISS.directive_schema, {
                'Human': 'NewHuman', 'Droid': 'NewDroid', 'stitch': 'NewStitch'
            }
        )
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewHuman {
              id: String
            }

            type NewDroid {
              id: String
              friend: NewHuman @stitch(source_field: "id", sink_field: "id")
            }

            directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

            type SchemaQuery {
              NewHuman: NewHuman
              NewDroid: NewDroid
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewHuman': 'Human', 'NewDroid': 'Droid'},
                         renamed_schema.reverse_name_map)

    def test_all_clashing_rename(self):
        class ConstantDict(object):
            def __contains__(self, key):
                return True

            def get(self, key, default=None):
                return 'OneType'

        with self.assertRaises(SchemaRenameConflictError):
            rename_schema(ISS.list_schema, ConstantDict())

    def test_clashing_type_rename(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human1 {
              id: String
            }

            type Human2 {
              id: String
            }

            type SchemaQuery {
              Human1: Human1
              Human2: Human2
            }
        ''')

        with self.assertRaises(SchemaRenameConflictError):
            rename_schema(schema_string, {'Human1': 'Human', 'Human2': 'Human'})

    def test_clashing_type_single_rename(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type Human2 {
              id: String
            }

            type SchemaQuery {
              Human: Human
              Human2: Human2
            }
        ''')

        with self.assertRaises(SchemaRenameConflictError):
            rename_schema(schema_string, {'Human2': 'Human'})

    def test_clashing_type_one_unchanged_rename(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type Human2 {
              id: String
            }

            type SchemaQuery {
              Human: Human
              Human2: Human2
            }
        ''')

        with self.assertRaises(SchemaRenameConflictError):
            rename_schema(schema_string, {'Human': 'Human', 'Human2': 'Human'})

    def test_clashing_scalar_type_rename(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            scalar SCALAR

            type SchemaQuery {
              Human: Human
            }
        ''')

        with self.assertRaises(SchemaRenameConflictError):
            rename_schema(schema_string, {'Human': 'SCALAR'})

    def test_builtin_type_conflict_rename(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type SchemaQuery {
              Human: Human
            }
        ''')

        with self.assertRaises(SchemaRenameConflictError):
            rename_schema(schema_string, {'Human': 'String'})

    def test_schema_extension(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Human: Human
            }

            type Human {
              id: String
            }

            extend type Human {
              age: Int
            }
        ''')
        with self.assertRaises(SchemaStructureError):
            rename_schema(schema_string, {})

    def test_input_type_definition(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              id: String
            }

            input MessageInput {
              content: String
            }
        ''')
        with self.assertRaises(SchemaStructureError):
            rename_schema(schema_string, {})

    def test_mutation_definition(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
              mutation: SchemaMutation
            }

            type SchemaQuery {
              id: String
            }

            type SchemaMutation {
              addId(id: String): String
            }
        ''')
        with self.assertRaises(SchemaStructureError):
            rename_schema(schema_string, {})

    def test_subscription_definition(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
              subscription: SchemaSubscription
            }

            type SchemaQuery {
              id: String
            }

            type SchemaSubscription {
              getId: String
            }
        ''')
        with self.assertRaises(SchemaStructureError):
            rename_schema(schema_string, {})

    def test_inconsistent_root_field_name(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human1 {
              id: String
            }

            type Human2 {
              id: String
            }

            type SchemaQuery {
              human1: Human1
              human2: Human2
            }
        ''')

        with self.assertRaises(SchemaStructureError):
            rename_schema(schema_string, {})

    def test_various_types_rename(self):
        class AddNewDict(object):
            def __contains__(self, key):
                return True

            def get(self, key, default=None):
                return 'New' + key

        renamed_schema = rename_schema(ISS.various_types_schema, AddNewDict())
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            scalar Date

            enum NewHeight {
              TALL
              SHORT
            }

            interface NewCharacter {
              id: String
            }

            type NewHuman implements NewCharacter {
              id: String
              name: String
              birthday: Date
            }

            type NewGiraffe implements NewCharacter {
              id: String
              height: NewHeight
            }

            directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

            type SchemaQuery {
              NewHuman: NewHuman
              NewGiraffe: NewGiraffe
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewCharacter': 'Character', 'NewGiraffe': 'Giraffe',
                          'NewHeight': 'Height', 'NewHuman': 'Human'},
                         renamed_schema.reverse_name_map)
