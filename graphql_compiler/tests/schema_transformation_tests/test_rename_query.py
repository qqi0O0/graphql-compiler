# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast

from graphql_compiler.schema_transformation.rename_query import rename_query

from .input_schema_strings import InputSchemaStrings as ISS


class TestDemangleQuery(unittest.TestCase):
    def test_no_rename(self):
        query_string = dedent('''\
            query HumanIdQuery {
              Human {
                id
              }
            }
        ''')
        renamed_query = rename_query(parse(query_string), {})
        self.assertEqual(query_string, print_ast(renamed_query))

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

    def test_original_unmodified(self):
        query_string = dedent('''\
            query HumanIdQuery {
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

    def test_rename_nested_query(self):
        query_string = dedent('''\
            query NestedQuery {
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
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'name': 'Name',
                'id': 'Id',
            }
        )
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
            query FetchLukeAliased {
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
            query FetchLukeAliased {
              luke: NewHuman(id: "1000") {
                name
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_multiple_aliases(self):
        query_string = dedent('''\
            query FetchLukeAndLeiaAliased {
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
        query_string = dedent('''\
            query UseFragment {
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
        renamed_query = rename_query(
            parse(query_string),
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
        query_string = dedent('''\
            query FieldInInlineFragment {
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

    def test_nested_fragments(self):
        query_string = dedent('''\
            query Query {
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
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'name': 'Name',
                'age': 'Age',
            }
        )
        renamed_query_string = dedent('''\
            query Query {
              NewHuman {
                ...HumanInfoFragment
              }
            }

            fragment HumanInfoFragment on NewHuman {
              name
              ...HumanAgeFragment
            }

            fragment HumanAgeFragment on NewHuman {
              age
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_nested_fragment_with_inline(self):
        query_string = dedent('''\
            query Query {
              Character {
                name
                ...CharacterFragment
              }
            }

            fragment CharacterFragment on Character {
              id
              ... on Human {
                age
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            {
                'Human': 'NewHuman',
                'Character': 'NewCharacter',
                'CharacterFragment': 'NewCharacterFragment',
                'name': 'Name',
                'id': 'Id',
                'age': 'Age',
            }
        )
        renamed_query_string = dedent('''\
            query Query {
              NewCharacter {
                name
                ...CharacterFragment
              }
            }

            fragment CharacterFragment on NewCharacter {
              id
              ... on NewHuman {
                age
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

    # TODO:
    # ObjectField, ObjectValue (unclear)
