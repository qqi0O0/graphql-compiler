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

class TestMergeSchemas(unittest.TestCase):
    def test_no_rename_basic_merge(self):
        merged_schema = MergedSchema([(basic_schema, 'basic'), (enum_schema, 'enum')])
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
        self.assertEqual(set(), merged_schema.scalars)
        self.assertEqual(set(), merged_schema.directives)

    def test_rename_basic_merge(self):
        merged_schema = MergedSchema([(basic_schema, 'first', lambda name: 'First' + name),
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
        self.assertEqual(set(), merged_schema.scalars)
        self.assertEqual(set(), merged_schema.directives)
