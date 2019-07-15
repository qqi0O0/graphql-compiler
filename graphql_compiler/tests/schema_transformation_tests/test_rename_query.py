# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast

from graphql_compiler.schema_transformation.rename_query import rename_query

from .input_query_strings import InputQueryStrings as IQS
from .input_schema_strings import InputSchemaStrings as ISS


class TestDemangleQuery(unittest.TestCase):
    def test_no_rename(self):
        renamed_query = rename_query(parse(IQS.basic_named_query), {})
        self.assertEqual(IQS.basic_named_query, print_ast(renamed_query))

    def test_rename_named_query(self):
        renamed_query = rename_query(parse(IQS.basic_named_query),
                                     {'Human': 'NewHuman', 'HumanIdQuery': 'NewHumanIdQuery'})
        renamed_query_string = dedent('''\
            query HumanIdQuery {
              NewHuman {
                id
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_original_unmodified(self):
        ast = parse(IQS.basic_named_query)
        rename_query(parse(IQS.basic_named_query), {'Human': 'NewHuman'})
        self.assertEqual(ast, parse(IQS.basic_named_query))

    def test_rename_unnamed_query(self):
        renamed_query = rename_query(parse(IQS.basic_unnamed_query), {'Human': 'NewHuman'})
        renamed_query_string = dedent('''\
            {
              NewHuman {
                id
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_rename_nested_query(self):
        renamed_query = rename_query(parse(IQS.nested_query),
                                     {'Human': 'NewHuman', 'name': 'Name', 'friends': 'Friends'})
        renamed_query_string = dedent('''\
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
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_field_with_argument(self):
        query_string = dedent('''\
            query FetchByIdQuery {
              Human(id: "1000") {
                name
              }
            }
        ''')
        renamed_query = rename_query(parse(query_string), {'Human': 'NewHuman'})
        renamed_query_string = dedent('''\
            query FetchByIdQuery {
              NewHuman(id: "1000") {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_field_with_parameterized_argument(self):
        query_string = dedent('''\
            query FetchSomeIDQuery($someId: String!) {
              Human(id: $someId) {
                name
              }
            }
        ''')
        renamed_query = rename_query(parse(query_string), {'Human': 'NewHuman'})
        renamed_query_string = dedent('''\
            query FetchSomeIDQuery($someId: String!) {
              NewHuman(id: $someId) {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_single_alias_query(self):
        renamed_query = rename_query(parse(IQS.alias_query), {'Human': 'NewHuman', 'luke': 'Luke'})
        renamed_query_string = dedent('''\
            query FetchLukeAliased {
              luke: NewHuman(id: "1000") {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_multiple_aliases_queries(self):
        renamed_query = rename_query(parse(IQS.multiple_aliases_query), {'Human': 'NewHuman'})
        renamed_query_string = dedent('''\
            query FetchLukeAndLeiaAliased {
              luke: NewHuman(id: "1000") {
                name
              }
              leia: NewHuman(id: "1003") {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_fragment(self):
        renamed_query = rename_query(
            parse(IQS.fragment_query),
            {
                'Human': 'NewHuman',
                'HumanFragment': 'NewHumanFragment',
                'name': 'Name',
            }
        )
        renamed_query_string = dedent('''\
            query UseFragment {
              luke: NewHuman(id: "1000") {
                ...HumanFragment
              }
              leia: NewHuman(id: "1003") {
                ...HumanFragment
              }
            }

            fragment HumanFragment on NewHuman {
              name
              homePlanet
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_inline_fragment(self):
        renamed_query = rename_query(parse(IQS.inline_fragment_query),
                                     {'Human': 'NewHuman', 'Character': 'NewCharacter'})
        renamed_query_string = dedent('''\
            query FieldInInlineFragment {
              NewCharacter {
                name
                ... on NewHuman {
                  age
                }
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    # SelectionSet and Field very common

    # TODO: 
    # ObjectField, ObjectValue (unclear)
    # Variable, VariableDefinition (unclear)
    # TODO:
    # Introspection queries -- builtin types and root fields
