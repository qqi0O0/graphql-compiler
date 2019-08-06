# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse, print_ast
from graphql_compiler.exceptions import GraphQLValidationError
from graphql_compiler.schema_transformation.split_query import split_query

from .example_schema import basic_merged_schema, interface_merged_schema


class TestSplitQuery(unittest.TestCase):
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

    def _check_simple_parent_child_structure(
        self, merged_schema, full_query_str, parent_str, parent_field_path,
        parent_schema_id, child_str, child_field_path, child_schema_id
    ):
        """Check the query splits into a parent with one child, with specified attributes."""
        parent_query_node = split_query(parse(full_query_str), merged_schema)
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
              Animal {
                out_Animal_Creature {
                  age
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0]
        child_str = dedent('''\
            {
              Creature {
                age
                creature_name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 1]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_existing_output_field_in_parent(self):
        query_str = dedent('''\
            {
              Animal {
                name @output(out_name: "result")
                out_Animal_Creature {
                  age
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name @output(out_name: "result")
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0]
        child_str = dedent('''\
            {
              Creature {
                age
                creature_name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 1]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_existing_output_field_in_child(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  creature_name @output(out_name: "result")
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0]
        child_str = dedent('''\
            {
              Creature {
                creature_name @output(out_name: "result")
                age @output(out_name: "age")
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 0]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_existing_field_in_both(self):
        query_str = dedent('''\
            {
              Animal {
                name
                out_Animal_Creature {
                  creature_name @output(out_name: "result")
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0]
        child_str = dedent('''\
            {
              Creature {
                creature_name @output(out_name: "result")
                age @output(out_name: "age")
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 0]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_more_complex_structure(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_ParentOf {
                  color @output(out_name: "color")
                  out_Animal_Creature {
                    age @output(out_name: "age1")
                    out_Creature_ParentOf {
                      age @output(out_name: "age2")
                    }
                  }
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                out_Animal_ParentOf {
                  color @output(out_name: "color")
                  name
                }
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0, 'selection_set', 'selections', 1]
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age1")
                out_Creature_ParentOf {
                  age @output(out_name: "age2")
                }
                creature_name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 2]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_existing_optional_on_edge(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature @optional {
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name @optional
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0]
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                creature_name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 1]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_existing_optional_on_edge_and_field(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature @optional {
                  age @output(out_name: "age")
                }
                name @optional
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name @optional
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 1]
        # NOTE: the last index is 1, because there is a None occupying index 0
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                creature_name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 1]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_existing_directives_on_edge_moved_to_field(self):
        query_str = dedent('''\
            {
              Animal {
                name @output(out_name: "result")
                out_Animal_Creature @optional {
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name @output(out_name: "result") @optional
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0]
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                creature_name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 1]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_unsupported_directives(self):
        query_str = dedent('''\
            {
              Animal {
                color @tag(tag_name: "color")
                out_Animal_ParentOf {
                  color @filter(op_name: "=", value: ["%color"])
                        @output(out_name: "result")
                }
              }
            }
        ''')
        with self.assertRaises(GraphQLValidationError):
            split_query(parse(query_str), basic_merged_schema)

        query_str = dedent('''\
            {
              Animal @fold {
                color @output(out_name: "result")
              }
            }
        ''')
        with self.assertRaises(GraphQLValidationError):
            split_query(parse(query_str), basic_merged_schema)

        query_str = dedent('''\
            {
              Animal {
                out_Animal_ParentOf @recurse(depth: 1) {
                  color @output(out_name: "result")
                }
              }
            }
        ''')
        with self.assertRaises(GraphQLValidationError):
            split_query(parse(query_str), basic_merged_schema)

    def test_invalid_query_nonexistent_field(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  thing
                }
              }
            }
        ''')
        with self.assertRaises(GraphQLValidationError):
            split_query(parse(query_str), basic_merged_schema)

    def test_type_coercion_before_edge(self):
        query_str = dedent('''\
            {
              Entity {
                uuid
                ... on Animal {
                  out_Animal_Creature {
                    age @output(out_name: "age")
                  }
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Entity {
                uuid
                ... on Animal {
                  name
                }
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 1, 'selection_set', 'selections', 0]
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                creature_name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 1]

        self._check_simple_parent_child_structure(
            basic_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_interface_type_coercion_after_edge(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  ... on Cat {
                    age @output(out_name: "age")
                  }
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name
              }
            }
        ''')
        parent_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                             'selections', 0]
        child_str = dedent('''\
            {
              Cat {
                age @output(out_name: "age")
                creature_name
              }
            }
        ''')
        child_field_path = ['definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
                            'selections', 1]

        self._check_simple_parent_child_structure(
            interface_merged_schema, query_str, parent_str, parent_field_path, 'first',
            child_str, child_field_path, 'second'
        )

    def test_union_type_coercion_after_edge(self):
        pass
        # TODO
        # TODO: tests for interfaces and union type coercions
        # TODO: tests where the structure is more than just parent-child relation
