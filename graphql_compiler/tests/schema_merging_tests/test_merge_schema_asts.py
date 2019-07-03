# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast

from graphql_compiler.schema_merging.merge_schema_asts import merge_schema_asts

from .input_schema_strings import InputSchemaStrings as ISS


class TestMergeSchemaASTs(unittest.TestCase):
    def test_no_conflict_merge(self):
        ast1 = parse(ISS.basic_schema)
        ast2 = parse(ISS.enum_schema)
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
