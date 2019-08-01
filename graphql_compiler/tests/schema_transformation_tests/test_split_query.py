# Copyright 2019-present Kensho Technologies, LLC.
from collections import OrderedDict
from textwrap import dedent
import unittest

from graphql import parse, print_ast
from graphql_compiler.schema_transformation.split_query import split_query

from .example_schema import basic_merged_schema


class TestSplitQuery(unittest.TestCase):
    def test_basic_split(self):
        query_str = dedent('''\
            {
              Human {
                out_Human_Person {
                  name
                }
              }
            }
        ''')
        print(query_str)
        query_node = split_query(parse(query_str), basic_merged_schema)
        print(query_node)
        print(print_ast(query_node.query_ast))
        print(query_node.child_query_connections)
        for child_query_connection in query_node.child_query_connections:
            print(print_ast(child_query_connection.sink_query_node.query_ast))
        print()
        print()

    def test_existing_field_in_parent(self):
        query_str = dedent('''\
            {
              Human {
              id
                out_Human_Person {
                  name
                }
              }
            }
        ''')

    def test_existing_output_field_in_parent(self):
        query_str = dedent('''\
            {
              Human {
              id @output(out_name: "result")
                out_Human_Person {
                  name
                }
              }
            }
        ''')

    def test_existing_field_in_child(self):
        query_str = dedent('''\
            {
              Human {
                out_Human_Person {
                  identifier 
                  name
                }
              }
            }
        ''')

    def test_existing_output_field_in_child(self):
        query_str = dedent('''\
            {
              Human {
                out_Human_Person {
                  identifier @output(out_name: "result")
                  name
                }
              }
            }
        ''')

    def test_existing_field_in_both(self):
        query_str = dedent('''\
            {
              Human {
                id
                out_Human_Person {
                  identifier 
                  name
                }
              }
            }
        ''')

    def test_existing_field_in_both(self):
        query_str = dedent('''\
            {
              Human {
                id @output(out_name: "result1")
                out_Human_Person {
                  identifier @output(out_name: "result2")
                  name
                }
              }
            }
        ''')
        print(query_str)
        query_node = split_query(parse(query_str), basic_merged_schema)
        print(query_node)
        print(print_ast(query_node.query_ast))
        print(query_node.child_query_connections)
        for child_query_connection in query_node.child_query_connections:
            print(print_ast(child_query_connection.sink_query_node.query_ast))
        print()
        print()
