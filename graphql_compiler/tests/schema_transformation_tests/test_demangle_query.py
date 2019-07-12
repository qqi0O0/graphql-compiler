# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse

from graphql_compiler.schema_transformation.demangle_query import demangle_query

from .input_schema_strings import InputSchemaStrings as ISS
from .input_query_strings import InputQueryStrings as IQS


class TestDemangleQuery(unittest.TestCase):
    def test_no_rename_named_query_demangle(self):
        print()
        print(parse(IQS.basic_named_query))

    def test_no_rename_unnamed_query_demangle(self):
        print()
        print(parse(IQS.basic_unnamed_query))

    def test_no_rename_nested_query_demangle(self):
        print()
        print(parse(IQS.nested_query))

    def test_no_rename_named_query_demangle(self):
        query_string = dedent('''\
            query HumandIdQuery {
              NewHuman {
                id
              }
            }
        ''')

    def test_no_rename_unnamed_query_demangle(self):
        query_string = dedent('''\
            {
              NewHuman {
                id
              }
            }
        ''')

    def test_no_rename_nested_query_demangle(self):
        query_string = dedent('''\
            query NestedQuery {
              NewHuman {
                name
                friends {
                  name
                  appearsIn
                  friends {
                    name
                  }
                }
              }
            }
        ''')


    # SelectionSet and Field very common

    # TODO: 
    # InlineFragment, FragmentDefinition, FragmentSpread
    # ObjectField, ObjectValue (unclear)
    # Variable, VariableDefinition (unclear)
    # TODO:
    # Introspection queries -- builtin types and root fields
    # aliases
