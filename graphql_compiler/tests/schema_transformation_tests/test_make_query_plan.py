"""
from textwrap import dedent
import unittest

from graphql import parse, print_ast

from ...schema_transformation.make_query_plan import make_query_plan, print_query_plan
from ...schema_transformation.split_query import SubQueryNode, QueryConnection
from .example_schema import basic_merged_schema


class TestModifySplitQuery(unittest.TestCase):
    # TODO: a few tests to check the structure of the output, a few tests to check observers
    # (like print_query_plan)

    def get_sub_query_node(self, existing_parent_directives, existing_child_directives):
        # These example nodes don't contain Nones, have tests where ASTs contain Nones
        parent_str = dedent('''\
            {{
              Animal {{
                uuid{}
              }}
            }}
        ''').format(existing_parent_directives)
        child_str = dedent('''\
            {{
              Creature {{
                age @output(out_name: "age")
                id{}
              }}
            }}
        ''').format(existing_child_directives)
        parent_node = SubQueryNode(parse(parent_str))
        child_node = SubQueryNode(parse(child_str))
        parent_node.schema_id = 'first'
        child_node.schema_id = 'second'
        parent_out_name = ''
        child_out_name = ''
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

    def _check_simple_parent_child_plan_structure(self, parent_plan, parent_str, parent_schema_id,
                                                  child_str, child_schema_id):
        self.assertEqual(print_ast(parent_plan.query_ast), parent_str)
        self.assertEqual(parent_plan.schema_id, parent_schema_id)
        self.assertIs(parent_plan.parent_query_plan, None)
        self.assertEqual(len(parent_plan.child_query_plans), 1)
        child_plan = parent_plan.child_query_plans[0]
        self.assertEqual(print_ast(child_plan.query_ast), child_str)
        self.assertEqual(child_plan.schema_id, child_schema_id)
        self.assertIs(child_plan.parent_query_plan, parent_plan)
        self.assertEqual(child_plan.child_query_plans, [])

    def test_basic_query_plan(self):
        query_plan_descriptor = make_query_plan(self.get_sub_query_node(
            u'', u''
        ))
        print(print_query_plan(query_plan_descriptor))
        self.assertEqual(query_plan_descriptor.intermediate_output_names, 
                         set(('__intermediate_output_0', '__intermediate_output_1')))
        # self.assertEqual(query_plan_descriptor.output_join_descriptors, '')
        query_plan = query_plan_descriptor.root_sub_query_plan
        parent_str = dedent('''\
            {
              Animal {
                uuid @output(out_name: "__intermediate_output_0")
              }
            }
        ''')
        child_str = dedent('''\
            {
              Creature {
                age @output(out_name: "age")
                id @output(out_name: "__intermediate_output_1") \
@filter(op_name: "in_collection", value: ["$__intermediate_output_0"])
              }
            }
        ''')
        self._check_simple_parent_child_plan_structure(query_plan, parent_str, 'first',
                                                       child_str, 'second')

    def test_existing_output_on_parent(self):
        query_plan_descriptor = make_query_plan(self.get_sub_query_node(
            u' @output(out_name: "result")', u''
        ))
        self.assertEqual(query_plan_descriptor.intermediate_output_names, 
                         set(('__intermediate_output_0',)))
        # self.assertEqual(query_plan_descriptor.output_join_descriptors, '')
        query_plan = query_plan_descriptor.root_sub_query_plan
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
                age @output(out_name: "age")
                id @output(out_name: "__intermediate_output_0") \
@filter(op_name: "in_collection", value: ["$result"])
              }
            }
        ''')
        self._check_simple_parent_child_plan_structure(query_plan, parent_str, 'first',
                                                       child_str, 'second')

    # TODO: Test original unmodified


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

"""
