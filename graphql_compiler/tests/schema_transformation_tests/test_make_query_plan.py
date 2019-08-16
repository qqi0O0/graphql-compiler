from textwrap import dedent
import unittest

from graphql import parse, print_ast

from ...schema_transformation.make_query_plan import make_query_plan, print_query_plan
from ...schema_transformation.split_query import split_query
from .example_schema import basic_merged_schema


class TestMakeQueryPlan(unittest.TestCase):
    def test_basic(self):
        query_str = dedent('''\
            {
              Animal {
                out_Animal_Creature {
                  age @output(out_name: "age")
                }
              }
            }
        ''')
        query_node, intermediate_outputs = split_query(parse(query_str), basic_merged_schema)
        query_plan = make_query_plan(query_node, intermediate_outputs)
        print(print_query_plan(query_plan))
        print('original child:')
        print(print_ast(query_node.child_query_connections[0].sink_query_node.query_ast))
