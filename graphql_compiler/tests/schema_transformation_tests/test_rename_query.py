# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse

from graphql_compiler.schema_transformation.rename_query import rename_query

from .input_schema_strings import InputSchemaStrings as ISS
from .input_query_strings import InputQueryStrings as IQS


class TestDemangleQuery(unittest.TestCase):
    def test_no_rename_named_query(self):
        print()
        print(parse(IQS.basic_named_query))

    def test_no_rename_unnamed_query(self):
        print()
        print(parse(IQS.basic_unnamed_query))

    def test_no_rename_nested_query(self):
        print()
        print(parse(IQS.nested_query))

    def test_rename_named_query(self):
        query_string = dedent('''\
            query HumandIdQuery {
              NewHuman {
                id
              }
            }
        ''')
        pass

    def test_original_unmodified(self):
        pass

    def test_rename_unnamed_query(self):
        query_string = dedent('''\
            {
              NewHuman {
                id
              }
            }
        ''')
        pass

    def test_rename_nested_query(self):
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
        pass

    def test_field_with_argument(self):
        query_string = dedent('''\
            query FetchByIdQuery {
              NewHuman(id: "1000") {
                name
              }
            }
        ''')
        print()
        print(parse(query_string))

    def test_field_with_parameterized_argument(self):
        query_string = dedent('''\
            query FetchSomeIDQuery($someId: String!) {
              NewHuman(id: $someId) {
                name
              }
            }
        ''')
        print()
        print(parse(query_string))

    def test_single_alias_query(self):
        print()
        print(parse(IQS.alias_query))

    def test_multiple_alias_queries(self):
        print()
        print(parse(IQS.multiple_alias_query))


    # SelectionSet and Field very common

    # TODO: 
    # InlineFragment, FragmentDefinition, FragmentSpread
    # ObjectField, ObjectValue (unclear)
    # Variable, VariableDefinition (unclear)
    # TODO:
    # Introspection queries -- builtin types and root fields
    # aliases
