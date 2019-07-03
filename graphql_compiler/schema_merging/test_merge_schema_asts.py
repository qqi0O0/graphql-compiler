from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast

from .merge_schema_asts import merge_schema_asts
from .test_schemas import *


class TestMergeSchemaASTs(unittest.TestCase):
    def test_no_conflict_merge(self):
        ast1 = parse(basic_schema)
        ast2 = parse(enum_schema)
        merged_schema = dedent('''\
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
        self.assertEqual(merged_schema, print_ast(merge_schema_asts(ast1, ast2)))

    # TODO: merge more complex ASTs
    # can probably take tests from merge_schemas here or maybe just test it there
    # TODO: test tons of ways to make merge fail
