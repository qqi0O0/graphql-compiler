import unittest
from textwrap import dedent

from .schema_merging import *
from .test_schemas import *
from graphql.language.printer import print_ast
from graphql import parse

# Unit tests for each step in _modify_schema

# TODO: NonNullType

def get_dummy_schema():
    dummy_schema_string = dedent('''\
        schema {
          query: SchemaQuery
        }

        type SchemaQuery {
          DummyField: Boolean
        }
    ''')
    dummy_schema = MergedSchema([(dummy_schema_string, 'dummy_schema')])
    dummy_schema.reverse_root_field_id_map.pop('DummyField')
    return dummy_schema

class TestRenameTypes(unittest.TestCase):
    def test_no_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(basic_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: name, schema_data) 
        self.assertEqual(basic_schema, print_ast(ast))
        self.assertEqual({'Human': ('Human', 'schema')}, blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_basic_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(basic_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewHuman {
              id: String
            }

            type SchemaQuery {
              Human: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({'NewHuman': ('Human', 'schema')}, blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_enum_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(enum_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewDroid {
              height: NewHeight
            }

            type SchemaQuery {
              Droid: NewDroid
            }

            enum NewHeight {
              TALL
              SHORT
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({'NewDroid': ('Droid', 'schema'), 'NewHeight': ('Height', 'schema')},
                         blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_interface_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(interface_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
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
              Character: NewCharacter
              Human: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual(
            {'NewHuman': ('Human', 'schema'), 'NewCharacter': ('Character', 'schema')},
            blank_schema.reverse_name_id_map
        )
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_interfaces_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(interfaces_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
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
              Character: NewCharacter
              Creature: NewCreature
              Human: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual(
            {'NewHuman': ('Human', 'schema'), 'NewCharacter': ('Character', 'schema'),
             'NewCreature': ('Creature', 'schema')},
            blank_schema.reverse_name_id_map
        )
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_scalar_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(scalar_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewHuman {
              birthday: Date
            }

            scalar Date

            type SchemaQuery {
              Human: NewHuman
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({'NewHuman': ('Human', 'schema')}, blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_union_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(union_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
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
              Human: NewHuman
              Droid: NewDroid
              HumanOrDroid: NewHumanOrDroid
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({'NewHuman': ('Human', 'schema'), 'NewDroid': ('Droid', 'schema'),
                          'NewHumanOrDroid': ('HumanOrDroid', 'schema')},
                         blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_multiple_schemas_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(basic_schema)
        basic_schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'basic', lambda name: 'Basic' + name, basic_schema_data) 
        basic_renamed_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type BasicHuman {
              id: String
            }

            type SchemaQuery {
              Human: BasicHuman
            }
        ''')
        self.assertEqual(basic_renamed_schema, print_ast(ast))
        self.assertEqual({'BasicHuman': ('Human', 'basic')}, blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

        ast = parse(enum_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'enum', lambda name: 'Enum' + name, schema_data) 
        enum_renamed_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type EnumDroid {
              height: EnumHeight
            }

            type SchemaQuery {
              Droid: EnumDroid
            }

            enum EnumHeight {
              TALL
              SHORT
            }
        ''')
        self.assertEqual(enum_renamed_schema, print_ast(ast))
        self.assertEqual({'BasicHuman': ('Human', 'basic'), 'EnumDroid': ('Droid', 'enum'),
                          'EnumHeight': ('Height', 'enum')},
                         blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_lists_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(list_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
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
              Droid: [NewDroid]
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
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual(
            {'NewDroid': ('Droid', 'schema'), 'NewCharacter': ('Character', 'schema'),
             'NewHeight': ('Height', 'schema')},
            blank_schema.reverse_name_id_map
        )
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_directives_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(directives_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
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
              Human: NewHuman
              Droid: NewDroid
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({'NewHuman': ('Human', 'schema'), 'NewDroid': ('Droid', 'schema')},
                         blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)


class TestModifyQueryType(unittest.TestCase):
    def test_modify_query_no_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(basic_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._modify_query_type(ast, 'schema', lambda name: name, schema_data.query_type,
                                        'RootSchemaQuery')
        renamed_schema = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type Human {
              id: String
            }

            extend type RootSchemaQuery {
              Human: Human
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({}, blank_schema.reverse_name_id_map)
        self.assertEqual({'Human': ('Human', 'schema')}, blank_schema.reverse_root_field_id_map)

    def test_modify_query_basic_rename(self):
        blank_schema = get_dummy_schema()
        ast = parse(basic_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._modify_query_type(ast, 'schema', lambda name: 'New' + name,
                                        schema_data.query_type, 'RootSchemaQuery')
        renamed_schema = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type Human {
              id: String
            }

            extend type RootSchemaQuery {
              NewHuman: Human
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({}, blank_schema.reverse_name_id_map)
        self.assertEqual({'NewHuman': ('Human', 'schema')}, blank_schema.reverse_root_field_id_map)

    def test_modify_query_various_types(self):
        blank_schema = get_dummy_schema()
        ast = parse(various_types_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._modify_query_type(ast, 'schema', lambda name: 'New' + name,
                                        schema_data.query_type, 'RootSchemaQuery')
        renamed_schema = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            scalar Date

            enum Height {
              TALL
              SHORT
            }

            interface Character {
              id: String
            }

            type Human implements Character {
              id: String
              name: String
              birthday: Date
            }

            type Giraffe implements Character {
              id: String
              height: Height
            }

            extend type RootSchemaQuery {
              NewHuman: Human
              NewGiraffe: Giraffe
            }
        ''') 
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({}, blank_schema.reverse_name_id_map)
        self.assertEqual({'NewHuman': ('Human', 'schema'), 'NewGiraffe': ('Giraffe', 'schema')},
                         blank_schema.reverse_root_field_id_map)


class TestRemoveDuplicates(unittest.TestCase):
    # TODO: same thing for directives
    def test_dedup_no_scalars(self):
        blank_schema = get_dummy_schema()
        ast = parse(multiple_scalars_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._remove_duplicates_and_update(ast, schema_data.scalars, schema_data.directives)
        self.assertEqual(multiple_scalars_schema, print_ast(ast))
        self.assertEqual({'Date', 'DateTime', 'Decimal'}, blank_schema.scalars)

    def test_dedup_some_scalars(self):
        blank_schema = get_dummy_schema()
        blank_schema.scalars = {'DateTime', 'RandomScalar'}
        ast = parse(multiple_scalars_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._remove_duplicates_and_update(ast, schema_data.scalars, schema_data.directives)
        deduped_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            scalar Date

            scalar Decimal

            enum Height {
              TALL
              SHORT
            }

            interface Character {
              id: String
            }

            type Human implements Character {
              id: String
              name: String
              birthday: Date
            }

            type Giraffe implements Character {
              id: String
              height: Height
            }

            type SchemaQuery {
              Human: Human
              Giraffe: Giraffe
            }
        ''')
        self.assertEqual(deduped_schema, print_ast(ast))
        self.assertEqual({'Date', 'DateTime', 'Decimal', 'RandomScalar'}, blank_schema.scalars)

    def test_dedup_all_scalars(self):
        blank_schema = get_dummy_schema()
        blank_schema.scalars = {'Date', 'DateTime', 'Decimal'}
        ast = parse(multiple_scalars_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._remove_duplicates_and_update(ast, schema_data.scalars, schema_data.directives)
        deduped_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            enum Height {
              TALL
              SHORT
            }

            interface Character {
              id: String
            }

            type Human implements Character {
              id: String
              name: String
              birthday: Date
            }

            type Giraffe implements Character {
              id: String
              height: Height
            }

            type SchemaQuery {
              Human: Human
              Giraffe: Giraffe
            }
        ''')
        self.assertEqual(deduped_schema, print_ast(ast))
        self.assertEqual({'Date', 'DateTime', 'Decimal'}, blank_schema.scalars)
