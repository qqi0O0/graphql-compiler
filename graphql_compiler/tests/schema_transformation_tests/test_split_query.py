# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple
from textwrap import dedent
import unittest

from graphql import parse, print_ast

from ...exceptions import GraphQLValidationError
from ...schema_transformation.split_query import split_query
from .example_schema import (
    basic_merged_schema, interface_merged_schema, union_merged_schema, three_merged_schema
)


# The below namedtuple is used to check the structure of SubQueryNodes in tests
ExampleQueryNode = namedtuple(
    'ExampleQueryNode', (
        'query_str',
        'schema_id',
        'child_query_nodes_and_paths',
        # List[Tuple[ExampleQueryNode, List[Union[int, str]], List[Union[int, str]]]]
        # child example query node, parent field path, child field path
    )
)


# The path that all field paths share in common. This path reaches the list of root selections
# of the query
BASE_FIELD_PATH = [
    'definitions', 0, 'selection_set', 'selections', 0, 'selection_set', 'selections'
]


class TestSplitQuery(unittest.TestCase):
    def _check_query_node_structure(self, root_query_node, root_example_query_node):
        self.assertIs(root_query_node.parent_query_connection, None)
        self._check_query_node_structure_helper(root_query_node, root_example_query_node)

    def _check_query_node_structure_helper(self, query_node, example_query_node):
        # Check AST and id of the parent
        self.assertEqual(print_ast(query_node.query_ast), example_query_node.query_str)
        self.assertEqual(query_node.schema_id, example_query_node.schema_id)
        # Check number of children matches
        self.assertEqual(len(query_node.child_query_connections),
                         len(example_query_node.child_query_nodes_and_paths))
        for i in range(len(query_node.child_query_connections)):
            # Check child and parent connections
            child_query_connection = query_node.child_query_connections[i]
            child_query_node = child_query_connection.sink_query_node
            child_example_query_node, parent_field_path, child_field_path = \
                example_query_node.child_query_nodes_and_paths[i]
            self._check_query_node_edge(query_node, i, child_query_node, parent_field_path,
                                        child_field_path)
            # Recurse
            self._check_query_node_structure_helper(child_query_node, child_example_query_node)

    def _check_query_node_edge(self, parent_query_node, parent_to_child_edge_index,
                               child_query_node, parent_field_path, child_field_path):
        """Check the edge between parent and child is symmetric, with the right paths."""
        parent_to_child_connection = \
            parent_query_node.child_query_connections[parent_to_child_edge_index]
        child_to_parent_connection = child_query_node.parent_query_connection

        self.assertIs(parent_to_child_connection.sink_query_node, child_query_node)
        self.assertIs(child_to_parent_connection.sink_query_node, parent_query_node)
        self.assertEqual(parent_to_child_connection.source_field_path, parent_field_path)
        self.assertEqual(child_to_parent_connection.sink_field_path, parent_field_path)
        self.assertEqual(parent_to_child_connection.sink_field_path, child_field_path)
        self.assertEqual(child_to_parent_connection.source_field_path, child_field_path)

    # TODO: make these queries all legal with @output and such
    # test for bad property and vertex field order
    # test for edge cut off, new property field added NOT in place
    # type coercion in different places
    # Test like where the Cat type didn't have a corresponding root field

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
                uuid
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_existing_output_field_in_parent(self):
        query_str = dedent('''\
            {
              Animal {
                uuid @output(out_name: "result")
                out_Animal_Creature {
                  age
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                uuid @output(out_name: "result")
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_check_none_branch_removed(self):
        query_str = dedent('''\
            {
              Animal {
                uuid @output(out_name: "result")
                out_Animal_Creature {
                  age
                }
              }
            }
        ''')
        query_node = split_query(parse(query_str), basic_merged_schema)
        parent_ast = query_node.query_ast
        parent_root_selections = parent_ast.definitions[0].selection_set.selections[0].\
                selection_set.selections
        self.assertEqual(len(parent_root_selections), 1)  # check None in second position removed
        print(query_node.query_ast)  # TODO

    def test_existing_output_field_in_child(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  id @output(out_name: "result")
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                uuid
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                id @output(out_name: "result")
                age @output(out_name: "age")
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [0],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_existing_field_in_both(self):
        query_str = dedent('''\
            {
              Animal {
                uuid @filter(op_name: "in_collection", value: ["$uuids"])
                out_Animal_Creature {
                  id @output(out_name: "result")
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                uuid @filter(op_name: "in_collection", value: ["$uuids"])
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                id @output(out_name: "result")
                age @output(out_name: "age")
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [0],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_nested_query(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_ParentOf {
                  color @output(out_name: "color")
                  out_Animal_Creature {
                    age @output(out_name: "age1")
                    friend {
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
                  uuid
                }
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age1")
                id
                friend {
                  age @output(out_name: "age2")
                }
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0, 'selection_set', 'selections', 1],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

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
                uuid @optional
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_existing_optional_on_edge_and_field(self):
        query_str = dedent('''\
            {
              Animal {
                uuid @optional
                out_Animal_Creature @optional {
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                uuid @optional
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_existing_directives_on_edge_moved_to_field(self):
        query_str = dedent('''\
            {
              Animal {
                uuid @output(out_name: "result")
                out_Animal_Creature @optional {
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                uuid @output(out_name: "result") @optional
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

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
                  uuid
                }
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [1, 'selection_set', 'selections', 0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

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
                uuid
              }
            }
        ''')
        child_str = dedent('''\
            {
              Cat {
                age @output(out_name: "age")
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), interface_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_invalid_interface_type_coercion(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  ... on Company {
                    age @output(out_name: "age")
                  }
                }
              }
            }
        ''')
        with self.assertRaises(GraphQLValidationError):
            split_query(parse(query_str), interface_merged_schema)


    def test_union_type_coercion_after_edge(self):
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
                uuid
              }
            }
        ''')
        child_str = dedent('''\
            {
              Cat {
                age @output(out_name: "age")
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), union_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_invalid_union_type_coercion(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  ... on Company {
                    age @output(out_name: "age")
                  }
                }
              }
            }
        ''')
        with self.assertRaises(GraphQLValidationError):
            split_query(parse(query_str), union_merged_schema)

    def test_two_children_stitch_on_same_field(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  age
                }
                out_Animal_ParentOf {
                  out_Animal_Creature {
                    age
                  }
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                uuid
                out_Animal_ParentOf {
                  uuid
                }
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                ),
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [1, 'selection_set', 'selections', 0],
                    BASE_FIELD_PATH + [1],
                ),
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_complex_query_structure(self):
        query_str = dedent('''\
            {
              Animal {
                color @output(out_name: "color")
                out_Animal_Creature {
                  age @output(out_name: "age")
                  in_Animal_Creature {
                    description @output(out_name: "description")
                  }
                  friend {
                    in_Animal_Creature {
                      description @output(out_name: "friend_description")
                    }
                  }
                }
              }
            }
        ''')
        query_piece1_str = dedent('''\
            {
              Animal {
                color @output(out_name: "color")
                uuid
              }
            }
        ''')
        query_piece2_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                id
                friend {
                  id
                }
              }
            }
        ''')
        query_piece3_str = dedent('''\
            {
              Animal {
                description @output(out_name: "description")
                uuid
              }
            }
        ''')
        query_piece4_str = dedent('''\
            {
              Animal {
                description @output(out_name: "friend_description")
                uuid
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=query_piece1_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=query_piece2_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[
                            (
                                ExampleQueryNode(
                                    query_str=query_piece3_str,
                                    schema_id='first',
                                    child_query_nodes_and_paths=[]
                                ),
                                BASE_FIELD_PATH + [1],
                                BASE_FIELD_PATH + [1],
                            ),
                            (
                                ExampleQueryNode(
                                    query_str=query_piece4_str,
                                    schema_id='first',
                                    child_query_nodes_and_paths=[]
                                ),
                                BASE_FIELD_PATH + [2, 'selection_set', 'selections', 0],
                                BASE_FIELD_PATH + [1],
                            ),
                        ]
                    ),
                    BASE_FIELD_PATH + [1],
                    BASE_FIELD_PATH + [1],
                ),
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_path_after_removed_field(self):
        query_str = dedent('''\
            {
              Animal {
                uuid
                out_Animal_Creature {
                  age
                }
                out_Animal_ParentOf {
                  out_Animal_Creature {
                    age
                  }
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                uuid
                out_Animal_ParentOf {
                  uuid
                }
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                ),
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [1, 'selection_set', 'selections', 0],
                    BASE_FIELD_PATH + [1],
                ),
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_cross_schema_edge_field_after_normal_vertex_field(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_ParentOf {
                  color @output(out_name: "color")
                }
                out_Animal_Creature {
                  age
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                uuid
                out_Animal_ParentOf {
                  color @output(out_name: "color")
                }
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age
                id
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [0],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), basic_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_two_edges_on_same_field_in_V(self):
        query_str = dedent('''\
            {
              Animal {
                name
                out_Animal_Creature {
                  age
                }
                out_Animal_Critter {
                  size
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Animal {
                name
                uuid
              }
            }
        ''')
        child1_str = dedent('''\
            {
              Creature {
                age
                id
              }
            }
        ''')
        child2_str = dedent('''\
            {
              Critter {
                size
                ID
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='first',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child1_str,
                        schema_id='second',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [1],
                    BASE_FIELD_PATH + [1],
                ),
                (
                    ExampleQueryNode(
                        query_str=child2_str,
                        schema_id='third',
                        child_query_nodes_and_paths=[]
                    ),
                    BASE_FIELD_PATH + [1],
                    BASE_FIELD_PATH + [1],
                )
            ]
        )
        query_node = split_query(parse(query_str), three_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_two_edges_on_same_field_in_chain(self):
        query_str = dedent('''\
            {
              Creature {
                age
                in_Animal_Creature {
                  name
                  out_Animal_Critter {
                    size
                  }
                }
              }
            }
        ''')
        parent_str = dedent('''\
            {
              Creature {
                age
                id
              }
            }
        ''')
        child1_str = dedent('''\
            {
              Animal {
                name
                uuid
              }
            }
        ''')

        child2_str = dedent('''\
            {
              Critter {
                size
                ID
              }
            }
        ''')
        example_query_node = ExampleQueryNode(
            query_str=parent_str,
            schema_id='second',
            child_query_nodes_and_paths=[
                (
                    ExampleQueryNode(
                        query_str=child1_str,
                        schema_id='first',
                        child_query_nodes_and_paths=[
                            (
                                ExampleQueryNode(
                                    query_str=child2_str,
                                    schema_id='third',
                                    child_query_nodes_and_paths=[]
                                ),
                                BASE_FIELD_PATH + [1],
                                BASE_FIELD_PATH + [1],
                            )
                        ]
                    ),
                    BASE_FIELD_PATH + [1],
                    BASE_FIELD_PATH + [1],
                ),
            ]
        )
        query_node = split_query(parse(query_str), three_merged_schema)
        self._check_query_node_structure(query_node, example_query_node)

    def test_very_sad(self):
        query_str = dedent('''\
            {
              Animal {
                name
                friend {
                  out_E1 {
                    age
                  }
                }
                out_E2 {
                  color
                }
              }
            }
        ''')
        # Path completely fails

    # TODO: back and forth on an edge
