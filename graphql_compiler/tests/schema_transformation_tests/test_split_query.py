# Copyright 2019-present Kensho Technologies, LLC.
from collections import OrderedDict
from textwrap import dedent
import unittest

from graphql import parse, print_ast
from graphql.language import ast as ast_types
from graphql_compiler.schema_transformation.split_query import split_query

from .example_schema import basic_merged_schema


class TestSplitQuery(unittest.TestCase):
    # Add tests for interface and union
    # Proper way to test this is to test observers (query plan, etc)
    # Test original unmodified
    def _get_unique_element(self, elements_list):
        self.assertIsInstance(elements_list, list)
        self.assertEqual(len(elements_list), 1)
        return elements_list[0]

    def test_no_existing_fields_split(self):
        query_str = dedent('''\
            {
              Human {
                out_Human_Person {
                  name
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Human {
                id
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0]
        child_str = dedent('''\
            {
              Person {
                name
                identifier
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 1]

        parent_query_node = split_query(parse(query_str), basic_merged_schema)
        parent_to_child_connection = self._get_unique_element(
            parent_query_node.child_query_connections
        )
        child_query_node = parent_to_child_connection.sink_query_node
        child_to_parent_connection = child_query_node.parent_query_connection

        self.assertEqual(child_query_node.child_query_connections, [])

        self.assertEqual(print_ast(parent_query_node.query_ast), parent_str)
        self.assertEqual(print_ast(child_query_node.query_ast), child_str)
        self.assertIs(parent_query_node.parent_query_connection, None)
        self.assertIs(child_to_parent_connection.sink_query_node, parent_query_node)

        self.assertEqual(parent_to_child_connection.source_field_path, parent_field_path)
        self.assertEqual(parent_to_child_connection.sink_field_path, child_field_path)
        self.assertEqual(child_to_parent_connection.sink_field_path, parent_field_path)
        self.assertEqual(child_to_parent_connection.source_field_path, child_field_path)

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
        query_node = split_query(parse(query_str), basic_merged_schema)

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
        '''
        print(query_str)
        query_node = split_query(parse(query_str), basic_merged_schema)
        print(query_node)
        print(print_ast(query_node.query_ast))
        print(query_node.child_query_connections)
        for child_query_connection in query_node.child_query_connections:
            print(print_ast(child_query_connection.sink_query_node.query_ast))
        print()
        print()
        '''


class TestModifySplitQuery(unittest.TestCase):
    # Test original unmodified
    def test_basic_modify(self):
        query_str = dedent('''\
            {
              Human {
                out_Human_Person {
                  name
                }
              }
            }
        ''')

#        print(query_str)
#        query_ast = parse(query_str)
#        query_node = split_query(query_ast, basic_merged_schema)
#        query_node.add_output_and_filter_directives()
#        print(query_node.print_query_plan())

    def test_existing_outputs_modify(self):
        query_str = dedent('''\
            {
              Human {
                out_Human_Person {
                  name
                  identifier @output(out_name: "result")
                }
              }
            }
        ''')

#        print(query_str)
#        query_ast = parse(query_str)
#        query_node = split_query(query_ast, basic_merged_schema)
#        query_node.add_output_and_filter_directives()
#        print(query_node.print_query_plan())
