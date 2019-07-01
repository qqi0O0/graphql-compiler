from collections import OrderedDict
from .schema_merging import *
from .test_schemas import *
from textwrap import dedent
import unittest



"""
normal type/enum/interface conflict/no-conflict

RootSchemaQuery rename/no-rename

scalar overlap

directive overlap
"""


def _make_merged_schema(schemas_info):
    renamed_schemas_map = OrderedDict()
    for schema_info in schemas_info:
        if len(schema_info) == 2:
            renamed_schemas_map[schema_info[1]] = RenamedSchema(schema_info[0])
        elif len(schema_info) == 3:
            renamed_schemas_map[schema_info[1]] = RenamedSchema(schema_info[0], schema_info[2])
        else:
            raise AssertionError
    return MergedSchema(renamed_schemas_map)

class TestMergeSchemas(unittest.TestCase):
    def test_no_rename_basic_merge(self):
        merged_schema = _make_merged_schema([(basic_schema, 'basic'), (enum_schema, 'enum')])
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type Droid {
              height: Height
            }

            enum Height {
              SHORT
              TALL
            }

            type Human {
              id: String
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
            }
        ''')
        self.assertEqual(merged_schema_string, merged_schema.get_schema_string())
        self.assertEqual({'Droid': ('Droid', 'enum'), 'Height': ('Height', 'enum'),
                          'Human': ('Human', 'basic')},
                         merged_schema.reverse_name_id_map)
        self.assertEqual({'Human': ('Human', 'basic'), 'Droid': ('Droid', 'enum')},
                         merged_schema.reverse_root_field_id_map)

    def test_rename_basic_merge(self):
        merged_schema = _make_merged_schema([(basic_schema, 'first', lambda name: 'First' + name),
                                      (basic_schema, 'second', lambda name: 'Second' + name)])
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type FirstHuman {
              id: String
            }

            type RootSchemaQuery {
              FirstHuman: FirstHuman
              SecondHuman: SecondHuman
            }

            type SecondHuman {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, merged_schema.get_schema_string())
        self.assertEqual({'FirstHuman': ('Human', 'first'), 'SecondHuman': ('Human', 'second')},
                         merged_schema.reverse_name_id_map)
        self.assertEqual({'FirstHuman': ('Human', 'first'), 'SecondHuman': ('Human', 'second')},
                         merged_schema.reverse_root_field_id_map)

    def test_invalid_input_schema(self):
        with self.assertRaises(SchemaError):
            _make_merged_schema([(invalid_schema, 'invalid')])

    def test_type_conflict_merge(self):
        with self.assertRaises(SchemaError):
            _make_merged_schema([(basic_schema, 'first'), (basic_schema, 'second')])

    def test_interface_type_conflict_merge(self):
        interface_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }
            
            type SchemaQuery {
              IntQuery: Int
            }

            interface Human {
              id: String
            }
        ''')
        with self.assertRaises(SchemaError):
            _make_merged_schema([(basic_schema, 'basic'),
                                 (interface_conflict_schema, 'bad')])

    def test_enum_type_conflict_merge(self):
        enum_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }
            
            type SchemaQuery {
              IntQuery: Int
            }

            enum Human {
              CHILD
              ADULT
            }
        ''')
        with self.assertRaises(SchemaError):
            _make_merged_schema([(basic_schema, 'basic'),
                                 (enum_conflict_schema, 'bad')])

    def test_enum_interface_conflict_merge(self):
        enum_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }
            
            type SchemaQuery {
              IntQuery: Int
            }

            enum Character {
              FICTIONAL
              REAL
            }
        ''')
        with self.assertRaises(SchemaError):
            _make_merged_schema([(interface_schema, 'interface'),
                                 (enum_conflict_schema, 'bad')])

    def test_type_scalar_conflict_merge(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }
            
            type SchemaQuery {
              IntQuery: Int
            }

            scalar Human
        ''')
        with self.assertRaises(SchemaError):
            _make_merged_schema([(basic_schema, 'basic'),
                                 (scalar_conflict_schema, 'bad')])

    def test_interface_scalar_conflict_merge(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }
            
            type SchemaQuery {
              IntQuery: Int
            }

            scalar Character
        ''')
        with self.assertRaises(SchemaError):
            _make_merged_schema([(interface_schema, 'interface'),
                                 (scalar_conflict_schema, 'bad')])

    def test_enum_scalar_conflict_merge(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }
            
            type SchemaQuery {
              IntQuery: Int
            }

            scalar Height
        ''')
        with self.assertRaises(SchemaError):
            _make_merged_schema([(enum_schema, 'enum'),
                                 (scalar_conflict_schema, 'bad')])

    def test_rename_to_scalar_conflict_merge(self):
        with self.assertRaises(SchemaError):
            _make_merged_schema([(basic_schema, 'invalid', lambda name: 'String')])

    def test_dedup_scalars(self):
        extra_scalar_schema =  dedent('''\
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
        merged_schema = _make_merged_schema(
            [(scalar_schema, 'first', lambda name: 'First' + name),
             (extra_scalar_schema, 'second', lambda name: 'Second' + name)]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            scalar Date

            scalar Decimal

            type FirstHuman {
              birthday: Date
            }

            type RootSchemaQuery {
              FirstHuman: FirstHuman
              SecondKid: SecondKid
            }

            type SecondKid {
              height: Decimal
            }
        ''')
        self.assertEqual(merged_schema_string, merged_schema.get_schema_string())
        self.assertEqual({'FirstHuman': ('Human', 'first'), 'SecondKid': ('Kid', 'second')},
                         merged_schema.reverse_name_id_map)
        self.assertEqual({'FirstHuman': ('Human', 'first'), 'SecondKid': ('Kid', 'second')},
                         merged_schema.reverse_root_field_id_map)
    # TODO: same thing for directives
