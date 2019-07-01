import unittest
from textwrap import dedent

from .schema_merging import *
from .test_schemas import *
from graphql.language.printer import print_ast
from graphql import parse


# TODO: NonNull type

class TestRenameSchema(unittest.TestCase):
    def test_no_rename(self):
        renamed_schema = RenamedSchema(basic_schema)
        
        self.assertEqual(basic_schema, renamed_schema.schema_string)
        self.assertEqual({'Human': 'Human'}, renamed_schema.reverse_name_map)
        self.assertEqual({'Human': 'Human'}, renamed_schema.reverse_root_field_map)

    def test_basic_rename(self):
        renamed_schema = RenamedSchema(basic_schema, lambda name: 'New' + name)
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
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewHuman': 'Human'}, renamed_schema.reverse_name_map)
        self.assertEqual({'NewHuman': 'Human'}, renamed_schema.reverse_root_field_map)

    def test_enum_rename(self):
        renamed_schema = RenamedSchema(enum_schema, lambda name: 'New' + name)
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
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewDroid': 'Droid', 'NewHeight': 'Height'},
                         renamed_schema.reverse_name_map)
        self.assertEqual({'NewDroid': 'Droid'}, renamed_schema.reverse_root_field_map)

    def test_interface_rename(self):
        renamed_schema = RenamedSchema(interface_schema, lambda name: 'New' + name)
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
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewHuman': 'Human', 'NewCharacter': 'Character'},
                         renamed_schema.reverse_name_map)
        self.assertEqual({'NewHuman': 'Human', 'NewCharacter': 'Character'},
                         renamed_schema.reverse_root_field_map)

    def test_interfaces_rename(self):
        renamed_schema = RenamedSchema(interfaces_schema, lambda name: 'New' + name)
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            interface NewCharacter {
              id: String
            }

            interface NewCreature {
              age: Int
            }

            type NewHuman implements NewCharacter, NewCreature {
              id: String
              age: Int
            }

            type SchemaQuery {
              NewCharacter: NewCharacter
              NewCreature: NewCreature
              NewHuman: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewHuman': 'Human', 'NewCharacter': 'Character',
                          'NewCreature': 'Creature'},
                         renamed_schema.reverse_name_map)
        self.assertEqual({'NewHuman': 'Human', 'NewCharacter': 'Character',
                          'NewCreature': 'Creature'},
                         renamed_schema.reverse_root_field_map)

    def test_scalar_rename(self):
        renamed_schema = RenamedSchema(scalar_schema, lambda name: 'New' + name)
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
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewHuman': 'Human'}, renamed_schema.reverse_name_map)
        self.assertEqual({'NewHuman': 'Human'}, renamed_schema.reverse_root_field_map)

    def test_union_rename(self):
        renamed_schema = RenamedSchema(union_schema, lambda name: 'New' + name)
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewHuman {
              id: String
            }

            type NewDroid {
              id: String
            }

            union NewHumanOrDroid = NewHuman | NewDroid

            type SchemaQuery {
              NewHuman: NewHuman
              NewDroid: NewDroid
              NewHumanOrDroid: NewHumanOrDroid
            }
        ''')
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewHuman': 'Human', 'NewDroid': 'Droid',
                          'NewHumanOrDroid': 'HumanOrDroid'},
                         renamed_schema.reverse_name_map)
        self.assertEqual({'NewHuman': 'Human', 'NewDroid': 'Droid',
                          'NewHumanOrDroid': 'HumanOrDroid'},
                         renamed_schema.reverse_root_field_map)

    def test_list_rename(self):
        renamed_schema = RenamedSchema(list_schema, lambda name: 'New' + name)
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
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewCharacter': 'Character', 'NewDroid': 'Droid',
                          'NewHeight': 'Height'},
                         renamed_schema.reverse_name_map)
        self.assertEqual({'NewDroid': 'Droid'},
                         renamed_schema.reverse_root_field_map)

    def test_directive_rename(self):
        renamed_schema = RenamedSchema(directive_schema, lambda name: 'New' + name)
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
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewHuman': 'Human', 'NewDroid': 'Droid'},
                         renamed_schema.reverse_name_map)
        self.assertEqual({'NewHuman': 'Human', 'NewDroid': 'Droid'},
                         renamed_schema.reverse_root_field_map)

    def test_clashing_rename(self):
        with self.assertRaises(SchemaError):
            RenamedSchema(list_schema, lambda name: 'OneType')

    def test_clashing_root_field_rename(self):
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
        def rename_func(name):
            if name[0] == 'H':
                return 'Human'
            return name
        with self.assertRaises(SchemaError):
            RenamedSchema(schema_string, rename_func)

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
              human1: Human1
              human2: Human2
            }
        ''')
        def rename_func(name):
            if name[0] == 'h':
                return 'human'
            return name
        with self.assertRaises(SchemaError):
            RenamedSchema(schema_string, rename_func)

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
              human: Human
            }
        ''')
        def rename_func(name):
            if name == 'Human':
                return 'SCALAR'
            return name
        with self.assertRaises(SchemaError):
            RenamedSchema(schema_string, rename_func)

    def test_builtin_type_conflict_rename(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type SchemaQuery {
              human: Human
            }
        ''')
        def rename_func(name):
            if name == 'Human':
                return 'String'
            return name
        with self.assertRaises(SchemaError):
            RenamedSchema(schema_string, rename_func)

    def test_builtin_field_conflict_rename(self):
        schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type SchemaQuery {
              human: Human
            }
        ''')
        def rename_func(name):
            if name == 'human':
                return 'String'
            return name
        renamed_schema = RenamedSchema(schema_string, rename_func)
        renamed_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type SchemaQuery {
              String: Human
            }
        ''')
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'Human': 'Human'}, renamed_schema.reverse_name_map)
        self.assertEqual({'String': 'human'}, renamed_schema.reverse_root_field_map)

    def test_various_types_rename(self):
        renamed_schema = RenamedSchema(various_types_schema, lambda name: 'New' + name)
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
        self.assertEqual(renamed_schema_string, renamed_schema.schema_string)
        self.assertEqual({'NewCharacter': 'Character', 'NewGiraffe': 'Giraffe',
                          'NewHeight': 'Height', 'NewHuman': 'Human'},
                         renamed_schema.reverse_name_map)
        self.assertEqual({'NewHuman': 'Human', 'NewGiraffe': 'Giraffe'},
                         renamed_schema.reverse_root_field_map)
