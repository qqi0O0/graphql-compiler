from textwrap import dedent
import unittest

from graphql import parse

from ...schema_transformation.make_query_plan import make_query_plan, print_query_plan
from ...schema_transformation.split_query import SubQueryNode, QueryConnection
from .example_schema import basic_merged_schema


class TestModifySplitQuery(unittest.TestCase):
    def get_example_sub_query_node(self, existing_parent_directives, existing_child_directives):
        parent_str = dedent('''\
            {
              Animal {
                uuid{}
              }
            }
        ''').format(existing_parent_directives)
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "result")
                id{}
              }
            }
        ''').format(existing_child_directives)
        parent_node = SubQueryNode(parse(parent_str))
        child_node = SubQueryNode(parse(parent_str))
        parent_node.schema_id = 'first'
        child_node.schema_id = 'second'
        parent_field_path = [
            'definitions', 0, 'selection_set', 'selections', 0, 'selection_set', 'selections', 0
        ]
        child_field_path = [
            'definitions', 0, 'selection_set', 'selections', 0, 'selection_set', 'selections', 1
        ]
        parent_to_child_connection = QueryConnection(
            sink_query_node=child_node,
            source_field_path=parent_field_path,
            sink_field_path=child_field_path,
        )
        child_to_parent_connection = QueryConnection(
            sink_query_node=parent_node,
            source_field_path=child_field_path,
            sink_field_path=parent_field_path,
        )
        parent_node.child_query_connections.append(parent_to_child_connection)
        child_node.parent_query_connection = child_to_parent_connection
        return parent_node

    # TODO: Test original unmodified
    def test_basic_modify(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  age
                }
              }
            }
        ''')
        query_node = split_query(parse(query_str), basic_merged_schema)
        query_plan_descriptor = make_query_plan(query_node)
        print(print_query_plan(query_plan_descriptor))
#        print(query_str)
#        query_ast = parse(query_str)
#        query_node = split_query(query_ast, basic_merged_schema)
#        query_node.add_output_and_filter_directives()
#        print(query_node.print_query_plan())

    # TODO:
    # parent stitch field has/does not have output
    # child stitch field has/does not have output
    # child stitch field has/does not have existing filter
    # parent stitch field has/does not have optional
    # child stitch field has optional (impossible?)
    # 

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
