import unittest
from textwrap import dedent

from .schema_merging import *
from graphql.language.printer import print_ast
from graphql import parse


basic_schema = dedent('''\
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

enum_schema = dedent('''\
    schema {
      query: SchemaQuery
    }

    type Human {
      height: Height
    }

    type SchemaQuery {
      Human: Human
    }

    enum Height {
      TALL
      SHORT
    }
''')

interface_schema = dedent('''\
    schema {
      query: SchemaQuery
    }

    interface Character {
      id: String
    }

    type Human implements Character {
      name: String
    }

    type SchemaQuery {
      Character: Character
      Human: Human
    }
''')

scalar_schema = dedent('''\
    schema {
      query: SchemaQuery
    }

    type Human {
      birthday: Date
    }

    scalar Date

    type SchemaQuery {
      Human: Human
    }
''')

# TODO: directives :(
# TODO: check the scalar directives sets
# TODO: tests for name collisions between scalars and types, directives and types, etc


class TestRenameTypes(unittest.TestCase):
    def test_no_rename(self):
        blank_schema = MergedSchema([])
        ast = parse(basic_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: name, schema_data) 
        self.assertEqual(basic_schema, print_ast(ast))
        self.assertEqual({'Human': ('Human', 'schema')}, blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_basic_rename(self):
        blank_schema = MergedSchema([])
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
        blank_schema = MergedSchema([])
        ast = parse(enum_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._rename_types(ast, 'schema', lambda name: 'New' + name, schema_data) 
        renamed_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type NewHuman {
              height: NewHeight
            }

            type SchemaQuery {
              Human: NewHuman
            }

            enum NewHeight {
              TALL
              SHORT
            }
        ''')
        self.assertEqual(renamed_schema, print_ast(ast))
        self.assertEqual({'NewHuman': ('Human', 'schema'), 'NewHeight': ('Height', 'schema')},
                         blank_schema.reverse_name_id_map)
        self.assertEqual({}, blank_schema.reverse_root_field_id_map)

    def test_interface_rename(self):
        blank_schema = MergedSchema([])
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
              name: String
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
        
    def test_scalar_rename(self):
        blank_schema = MergedSchema([])
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


various_types_schema = dedent('''\
    schema {
      query: SchemaQuery
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
      name: String
      birthday: Date
    }

    type Giraffe implements Character {
      height: Height
    }

    type SchemaQuery {
      Human: Human
      Giraffe: Giraffe
    }
''')


class TestModifyQueryType(unittest.TestCase):
    def test_modify_query_no_rename(self):
        blank_schema = MergedSchema([])
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
        blank_schema = MergedSchema([])
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
        blank_schema = MergedSchema([])
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
              name: String
              birthday: Date
            }

            type Giraffe implements Character {
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


multiple_scalars_schema = dedent('''\
    schema {
      query: SchemaQuery
    }

    scalar Date

    scalar DateTime

    scalar Decimal

    enum Height {
      TALL
      SHORT
    }

    interface Character {
      id: String
    }

    type Human implements Character {
      name: String
      birthday: Date
    }

    type Giraffe implements Character {
      height: Height
    }

    type SchemaQuery {
      Human: Human
      Giraffe: Giraffe
    }
''')


class TestRemoveDuplicates(unittest.TestCase):
    # TODO: same thing for directives
    def test_dedup_no_scalars(self):
        blank_schema = MergedSchema([])
        ast = parse(multiple_scalars_schema)
        schema_data = blank_schema._get_schema_data(ast)
        blank_schema._remove_duplicates_and_update(ast, schema_data.scalars, schema_data.directives)
        self.assertEqual(multiple_scalars_schema, print_ast(ast))
        self.assertEqual({'Date', 'DateTime', 'Decimal'}, blank_schema.scalars)

    def test_dedup_some_scalars(self):
        blank_schema = MergedSchema([])
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
              name: String
              birthday: Date
            }

            type Giraffe implements Character {
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
        blank_schema = MergedSchema([])
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
              name: String
              birthday: Date
            }

            type Giraffe implements Character {
              height: Height
            }

            type SchemaQuery {
              Human: Human
              Giraffe: Giraffe
            }
        ''')
        self.assertEqual(deduped_schema, print_ast(ast))
        self.assertEqual({'Date', 'DateTime', 'Decimal'}, blank_schema.scalars)
