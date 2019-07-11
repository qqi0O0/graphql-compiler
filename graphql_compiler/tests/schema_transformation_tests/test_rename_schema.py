# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast
from graphql.language.visitor_meta import QUERY_DOCUMENT_KEYS

from graphql_compiler.schema_transformation.rename_schema import (
    RenameSchemaTypesVisitor, rename_schema
)
from graphql_compiler.schema_transformation.utils import (
    InvalidNameError, SchemaNameConflictError, SchemaStructureError
)

from .input_schema_strings import InputSchemaStrings as ISS


class TestRenameSchema(unittest.TestCase):
    def test_rename_visitor_type_coverage(self):
        """Check that all types are covered without overlap."""
        all_types = set(ast_type.__name__ for ast_type in QUERY_DOCUMENT_KEYS)
        type_sets = [RenameSchemaTypesVisitor.noop_types,
                     RenameSchemaTypesVisitor.check_name_validity_types,
                     RenameSchemaTypesVisitor.rename_types,
                     RenameSchemaTypesVisitor.unexpected_types,
                     RenameSchemaTypesVisitor.disallowed_types]
        type_sets_union = set()
        for type_set in type_sets:
            self.assertTrue(type_sets_union.isdisjoint(type_set))
            type_sets_union.update(type_set)
        self.assertEqual(all_types, type_sets_union)

    def test_no_rename(self):
        renamed_schema = rename_schema(parse(ISS.basic_schema), {})

        self.assertEqual(ISS.basic_schema, print_ast(renamed_schema.schema_ast))
        self.assertEqual({}, renamed_schema.reverse_name_map)

    def test_basic_rename(self):
        renamed_schema = rename_schema(parse(ISS.basic_schema), {'Human': 'NewHuman'})
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

    def test_original_unmodified(self):
        original_ast = parse(ISS.basic_schema)
        rename_schema(original_ast, {'Human': 'NewHuman'})
        self.assertEqual(original_ast, parse(ISS.basic_schema))

    def test_enum_rename(self):
        renamed_schema = rename_schema(parse(ISS.enum_schema),
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
        renamed_schema = rename_schema(parse(ISS.interface_schema),
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
            parse(ISS.interfaces_schema), {
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
        self.assertEqual({'NewHuman': 'Human', 'NewCharacter': 'Character'},
                         renamed_schema.reverse_name_map)

    def test_scalar_rename(self):
        renamed_schema = rename_schema(
            parse(ISS.scalar_schema), {
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
        renamed_schema = rename_schema(parse(ISS.union_schema),
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
            }
        ''')
        self.assertEqual(renamed_schema_string, print_ast(renamed_schema.schema_ast))
        self.assertEqual({'NewDroid': 'Droid', 'NewHumanOrDroid': 'HumanOrDroid'},
                         renamed_schema.reverse_name_map)

    def test_list_rename(self):
        renamed_schema = rename_schema(
            parse(ISS.list_schema), {
                'Droid': 'NewDroid', 'Character': 'NewCharacter', 'Height': 'NewHeight',
                'Date': 'NewDate', 'id': 'NewId', 'String': 'NewString'
            }
        )
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
        self.assertEqual(
            {'NewCharacter': 'Character', 'NewDroid': 'Droid', 'NewHeight': 'Height'},
            renamed_schema.reverse_name_map
        )

    def test_non_null_rename(self):
        renamed_schema = rename_schema(parse(ISS.non_null_schema), {'Human': 'NewHuman'})
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
            parse(ISS.directive_schema), {
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
            def get(self, key, default=None):
                return 'OneType'

        with self.assertRaises(SchemaNameConflictError):
            rename_schema(parse(ISS.list_schema), ConstantDict())

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

        with self.assertRaises(SchemaNameConflictError):
            rename_schema(parse(schema_string), {'Human1': 'Human', 'Human2': 'Human'})

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

        with self.assertRaises(SchemaNameConflictError):
            rename_schema(parse(schema_string), {'Human2': 'Human'})

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

        with self.assertRaises(SchemaNameConflictError):
            rename_schema(parse(schema_string), {'Human': 'Human', 'Human2': 'Human'})

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

        with self.assertRaises(SchemaNameConflictError):
            rename_schema(parse(schema_string), {'Human': 'SCALAR'})

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

        with self.assertRaises(SchemaNameConflictError):
            rename_schema(parse(schema_string), {'Human': 'String'})

    def test_invalid_schema(self):
        with self.assertRaises(SchemaStructureError):
            rename_schema(parse(ISS.invalid_schema), {})

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
            rename_schema(parse(schema_string), {})

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
            rename_schema(parse(schema_string), {})

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
            rename_schema(parse(schema_string), {})

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
            rename_schema(parse(schema_string), {})

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
            rename_schema(parse(schema_string), {})

    def test_illegal_double_underscore_name(self):
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(ISS.double_underscore_schema), {})

    def test_illegal_rename_start_with_number(self):
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(ISS.basic_schema), {'Human': '0Human'})

    def test_illegal_rename_contains_illegal_char(self):
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(ISS.basic_schema), {'Human': 'Human!'})
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(ISS.basic_schema), {'Human': 'H-uman'})
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(ISS.basic_schema), {'Human': 'H.uman'})

    def test_illegal_rename_to_double_underscore(self):
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(ISS.basic_schema), {'Human': '__Human'})

    def test_illegal_rename_to_reserved_name_type(self):
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(ISS.basic_schema), {'Human': '__Type'})

    def test_illegal_reserved_name_type(self):
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

            type __Type {
              id: String
            }
        ''')
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(schema_string), {})

    def test_illegal_reserved_name_enum(self):
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

            enum __Type {
              ENUM1
              ENUM2
            }
        ''')
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(schema_string), {})

    def test_illegal_reserved_name_scalar(self):
        # NOTE: such scalars will not appear in typemap!
        # See graphql/type/introspection for all reserved types
        # This edge case (scalar with reserved type name defined but not used) is the reason that
        # check_name_validity_types was added to RenameSchemaTypesVisitor
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

            scalar __Type
        ''')
        with self.assertRaises(InvalidNameError):
            rename_schema(parse(schema_string), {})

    def test_various_types_rename(self):
        class AddNewDict(object):
            def get(self, key, default=None):
                return 'New' + key

        renamed_schema = rename_schema(parse(ISS.various_types_schema), AddNewDict())
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
