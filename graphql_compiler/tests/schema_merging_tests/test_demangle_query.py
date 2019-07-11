# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql_compiler.schema_transformation.demangle_query import demangle_query

from .input_schema_strings import InputSchemaStrings as ISS


class TestDemangleQuery(unittest.TestCase):
    def test_basic_no_rename_demangle(self):
        query_string = dedent('''\
            query HumandIdQuery {
              Human {
                id
              }
            }
        ''')
