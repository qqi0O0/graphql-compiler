from textwrap import dedent
import unittest

from graphql import parse

from ...schema_transformation.make_query_plan import make_query_plan, print_query_plan
from ...schema_transformation.split_query import split_query
from .example_schema import basic_merged_schema


class TestModifySplitQuery(unittest.TestCase):
    # Test original unmodified
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
