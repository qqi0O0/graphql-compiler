# Copyright 2019-present Kensho Technologies, LLC.
from collections import OrderedDict
from textwrap import dedent
import unittest

from graphql import parse

from graphql_compiler.schema_transformation.split_query import split_query

#from .example_schema import basic_merged_schema


class TestSplitQuery(unittest.TestCase):
    def test_basic_split(self):
        query_str = dedent('''\
            {
              Human {
                out_Human_Person
              }
            }
        ''')
