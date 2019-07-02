from collections import OrderedDict
from .schema_merging import *
from .test_schemas import *
from textwrap import dedent
import unittest

# TODO: test the observers


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
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type SchemaQuery {
              Human: Human
              Droid: Droid
            }

            type Droid {
              height: Height
            }

            enum Height {
              TALL
              SHORT
            }
        ''')
        self.assertEqual(merged_schema_string, merged_schema.schema_string)
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
              query: SchemaQuery
            }

            type FirstHuman {
              id: String
            }

            type SchemaQuery {
              FirstHuman: FirstHuman
              SecondHuman: SecondHuman
            }

            type SecondHuman {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, merged_schema.schema_string)
        self.assertEqual({'FirstHuman': ('Human', 'first'), 'SecondHuman': ('Human', 'second')},
                         merged_schema.reverse_name_id_map)
        self.assertEqual({'FirstHuman': ('Human', 'first'), 'SecondHuman': ('Human', 'second')},
                         merged_schema.reverse_root_field_id_map)

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
        merged_schema = _make_merged_schema([(basic_schema, 'first'),
                                             (diff_query_type_schema, 'second')])
        merged_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type SchemaQuery {
              Human: Human
              Droid: Droid
            }

            type Droid {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, merged_schema.schema_string)

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
        merged_schema = _make_merged_schema(
            [(scalar_schema, 'first', lambda name: 'First' + name),
             (extra_scalar_schema, 'second', lambda name: 'Second' + name)]
        )
        merged_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type FirstHuman {
              birthday: Date
            }

            scalar Date

            type SchemaQuery {
              FirstHuman: FirstHuman
              SecondKid: SecondKid
            }

            scalar Decimal

            type SecondKid {
              height: Decimal
            }
        ''')
        self.assertEqual(merged_schema_string, merged_schema.schema_string)
        self.assertEqual({'FirstHuman': ('Human', 'first'), 'SecondKid': ('Kid', 'second')},
                         merged_schema.reverse_name_id_map)
        self.assertEqual({'FirstHuman': ('Human', 'first'), 'SecondKid': ('Kid', 'second')},
                         merged_schema.reverse_root_field_id_map)

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
        merged_schema = _make_merged_schema(
            [(directive_schema, 'first'), (extra_directive_schema, 'second')]
        )
        merged_schema_string = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Human {
              id: String
            }

            type Droid {
              id: String
              friend: Human @stitch(source_field: "id", sink_field: "id")
            }

            directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

            type SchemaQuery {
              Human: Human
              Droid: Droid
              Kid: Kid
            }

            directive @output(out_name: String!) on FIELD

            type Kid {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, merged_schema.schema_string)
        self.assertEqual({'Human': ('Human', 'first'), 'Droid': ('Droid', 'first'),
                          'Kid': ('Kid', 'second')},
                         merged_schema.reverse_name_id_map)
        self.assertEqual({'Human': ('Human', 'first'), 'Droid': ('Droid', 'first'),
                          'Kid': ('Kid', 'second')},
                         merged_schema.reverse_root_field_id_map)
    # TODO: same thing for directives that clash


class TestSchemaObservers(unittest.TestCase):
    def test_no_rename_basic_merge(self):
        merged_schema = _make_merged_schema([(basic_schema, 'basic'), (enum_schema, 'enum')])
        self.assertEqual(merged_schema.get_original_type('Human', 'basic'), 'Human')
        self.assertEqual(merged_schema.get_original_type('Droid', 'enum'), 'Droid')
        with self.assertRaises(SchemaError):
            merged_schema.get_original_type('Human', 'enum')
        with self.assertRaises(SchemaError):
            merged_schema.get_original_type('Human', 'fake')
        with self.assertRaises(SchemaError):
            merged_schema.get_original_type('Fake', 'basic')
    # TODO same thing with renamed merge
