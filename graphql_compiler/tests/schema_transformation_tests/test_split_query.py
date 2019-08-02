# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse, print_ast
from graphql_compiler.schema_transformation.split_query import (
    print_query_plan, split_query, stabilize_and_add_directives
)

from .example_schema import basic_merged_schema


class TestSplitQuery(unittest.TestCase):
    # TODO: change to using standard test schemas
    # Add tests for interface and union
    # Proper way to test this is to test observers (query plan, etc)
    # Test original unmodified
    def _get_unique_element(self, elements_list):
        self.assertIsInstance(elements_list, list)
        self.assertEqual(len(elements_list), 1)
        return elements_list[0]

    def _check_query_node_edge(self, parent_query_node, parent_to_child_edge_index,
                               child_query_node):
        """Check the edge between parent and child are symmetric."""
        parent_to_child_connection = \
            parent_query_node.child_query_connections[parent_to_child_edge_index]
        child_to_parent_connection = child_query_node.parent_query_connection

        self.assertIs(parent_to_child_connection.sink_query_node, child_query_node)
        self.assertIs(child_to_parent_connection.sink_query_node, parent_query_node)
        self.assertEqual(parent_to_child_connection.source_field_path,
                         child_to_parent_connection.sink_field_path)
        self.assertEqual(parent_to_child_connection.sink_field_path,
                         child_to_parent_connection.source_field_path)

    def _check_simple_parent_child_structure(self, full_query_str, parent_str, parent_field_path,
                                             child_str, child_field_path):
        parent_query_node = split_query(parse(full_query_str), basic_merged_schema)
        parent_to_child_connection = self._get_unique_element(
            parent_query_node.child_query_connections
        )
        child_query_node = parent_to_child_connection.sink_query_node

        self._check_query_node_edge(parent_query_node, 0, child_query_node)

        self.assertEqual(print_ast(parent_query_node.query_ast), parent_str)
        self.assertEqual(print_ast(child_query_node.query_ast), child_str)

        self.assertEqual(child_query_node.child_query_connections, [])
        self.assertIs(parent_query_node.parent_query_connection, None)

        self.assertEqual(parent_to_child_connection.source_field_path, parent_field_path)
        self.assertEqual(parent_to_child_connection.sink_field_path, child_field_path)

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

        self._check_simple_parent_child_structure(query_str, parent_str, parent_field_path,
                                                  child_str, child_field_path)

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
        parent_str = dedent('''\
            {
              Human {
                id @output(out_name: "result")
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

        self._check_simple_parent_child_structure(query_str, parent_str, parent_field_path,
                                                  child_str, child_field_path)

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
                identifier @output(out_name: "result")
                name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 0]

        self._check_simple_parent_child_structure(query_str, parent_str, parent_field_path,
                                                  child_str, child_field_path)


    def test_existing_field_in_both(self):
        query_str = dedent('''\
            {
              Human {
                id
                out_Human_Person {
                  identifier @output(out_name: "result")
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
                identifier @output(out_name: "result")
                name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 0]

        self._check_simple_parent_child_structure(query_str, parent_str, parent_field_path,
                                                  child_str, child_field_path)

    def test_more_complex_structure(self):
        query_str = dedent('''\
            {
              Human {
                friend {
                  name @output(out_name: "name")
                  out_Human_Person {
                    age @output(out_name: "age")
                    enemy {
                      age @output(out_name: "enemy_age")
                    }
                  }
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Human {
                friend {
                  name @output(out_name: "name")
                  id
                }
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0, 'selection_set', 'selections', 1]
        child_str = dedent('''\
            {
              Person {
                age @output(out_name: "age")
                enemy {
                  age @output(out_name: "enemy_age")
                }
                identifier
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 2]

        self._check_simple_parent_child_structure(query_str, parent_str, parent_field_path,
                                                  child_str, child_field_path)

    # TODO: tests for interfaces and union type coercions

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
        query_node = split_query(parse(query_str), basic_merged_schema)
        stable_query_node, intermediate_outputs, connections = \
            stabilize_and_add_directives(query_node)
        
        print(query_str)
        print(print_query_plan(stable_query_node))
        print(intermediate_outputs)
        print(connections)
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
