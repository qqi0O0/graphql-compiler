# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast

from graphql_compiler.schema_transformation.rename_query import rename_query

from .input_schema_strings import InputSchemaStrings as ISS
from ...schema_transformation.utils import QueryStructureError


class TestDemangleQuery(unittest.TestCase):
    def test_no_rename(self):
        query_string = dedent('''\
            {
              Human {
                id
              }
            }
        ''')
        renamed_query = rename_query(parse(query_string), {})
        self.assertEqual(query_string, print_ast(renamed_query))

    def test_original_unmodified(self):
        query_string = dedent('''\
            {
              Human {
                id
              }
            }
        ''')
        ast = parse(query_string)
        rename_query(parse(query_string), {'Human': 'NewHuman'})
        self.assertEqual(ast, parse(query_string))

    def test_rename_unnamed_query(self):
        query_string = dedent('''\
           {
              Human {
                id
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'id': 'Id',
            }
        )
        renamed_query_string = dedent('''\
            {
              NewHuman {
                id
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_rename_named_query(self):
        query_string = dedent('''\
            query HumanIdQuery {
              Human {
                id
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'HumanIdQuery': 'NewHumanIdQuery',
                'id': 'Id',
            }
        )
        renamed_query_string = dedent('''\
            query HumanIdQuery {
              NewHuman {
                id
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_rename_nested_query(self):
        query_string = dedent('''\
            {
              Human {
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
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'name': 'Name',
                'frends': 'Friends',
            }
        )
        renamed_query_string = dedent('''\
            {
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
            {
              Human(id: "1000") {
                name
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'name': 'Name',
                'id': 'Id',
            }
        )
        renamed_query_string = dedent('''\
            {
              NewHuman(id: "1000") {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_field_with_parameterized_argument(self):
        query_string = dedent('''\
            query FetchIdQuery($id: String!) {
              Human(id: $id) {
                name
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'name': 'Name',
                'id': 'Id',
            }
        )
        renamed_query_string = dedent('''\
            query FetchIdQuery($id: String!) {
              NewHuman(id: $id) {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_single_alias(self):
        query_string = dedent('''\
            {
              luke: Human(id: "1000") {
                name
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'luke': 'Luke',
                'name': 'Name',
            }
        )
        renamed_query_string = dedent('''\
            {
              luke: NewHuman(id: "1000") {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_multiple_aliases(self):
        query_string = dedent('''\
            {
              luke: Human(id: "1000") {
                name
              }
              leia: Human(id: "1003") {
                name
              }
            }
        ''')
        renamed_query = rename_query(parse(query_string), {'Human': 'NewHuman'})
        renamed_query_string = dedent('''\
            {
              luke: NewHuman(id: "1000") {
                name
              }
              leia: NewHuman(id: "1003") {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))


    def test_inline_fragment(self):
        query_string = dedent('''\
            {
              Character {
                name
                ... on Human {
                  age
                }
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'Character': 'NewCharacter',
            }
        )
        renamed_query_string = dedent('''\
            {
              NewCharacter {
                name
                ... on NewHuman {
                  age
                }
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_nested_inline(self):
        query_string = dedent('''\
            {
              Character {
                friend {
                  ... on Human {
                    family {
                      ... on Child {
                        age
                      }
                    }
                  }
                }
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Character': 'NewCharacter',
                'Child': 'NewChild'
            }
        )
        renamed_query_string = dedent('''\
            {
              NewCharacter {
                friend {
                  ... on Human {
                    family {
                      ... on NewChild {
                        age
                      }
                    }
                  }
                }
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_directive(self):
        query_string = dedent('''\
            {
              Animal {
                name @output(out_name: "name")
                out_Entity_Related {
                  ... on Species {
                    description @output(out_name: "description")
                  }
                }
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Animal': 'NewAnimal',
                'Species': 'NewSpecies',
                'output': 'Output',
            }
        )
        renamed_query_string = dedent('''\
            {
              NewAnimal {
                name @output(out_name: "name")
                out_Entity_Related {
                  ... on NewSpecies {
                    description @output(out_name: "description")
                  }
                }
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_invalid_start_with_inline(self):
        query_string = dedent('''\
            {
              ... on RootSchemaQuery {
                Human {
                  name
                }
              }
            }
        ''')
        with self.assertRaises(QueryStructureError):
            rename_query(parse(query_string), {})

    def test_invalid_contains_fragment(self):
        query_string = dedent('''\
            {
              luke: Human(id: "1000") {
                ...HumanFragment
              }
              leia: Human(id: "1003") {
                ...HumanFragment
              }
            }

            fragment HumanFragment on Human {
              name
              homePlanet
            }
        ''')
        with self.assertRaises(QueryStructureError):
            rename_query(parse(query_string), {})

    def test_invalid_nested_fragments(self):
        query_string = dedent('''\
            {
              Human {
                ...HumanInfoFragment
              }
            }

            fragment HumanInfoFragment on Human {
              name
              ...HumanAgeFragment
            }

            fragment HumanAgeFragment on Human {
              age
            }
        ''')
        with self.assertRaises(QueryStructureError):
            rename_query(parse(query_string), {})

    # TODO:
    # ObjectField, ObjectValue (unclear)
