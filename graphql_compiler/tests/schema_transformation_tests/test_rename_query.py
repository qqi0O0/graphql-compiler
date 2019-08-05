# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast
from graphql_compiler.schema_transformation.rename_query import rename_query
from graphql_compiler.schema_transformation.rename_schema import rename_schema

from ...exceptions import GraphQLValidationError
from .input_schema_strings import InputSchemaStrings as ISS


# TODO: change to using the schema in helper
class TestRenameQuery(unittest.TestCase):
    def test_no_rename(self):
        query_string = dedent('''\
            {
              Human {
                id
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            rename_schema(parse(ISS.basic_schema), {})
        )
        self.assertEqual(query_string, print_ast(renamed_query))

    def test_original_unmodified(self):
        query_string = dedent('''\
            {
              NewHuman {
                id
              }
            }
        ''')
        ast = parse(query_string)
        renamed_query = rename_query(
            parse(query_string),
            rename_schema(parse(ISS.basic_schema), {'Human': 'NewHuman'})
        )
        self.assertEqual(ast, parse(query_string))

    def test_rename_unnamed_query(self):
        query_string = dedent('''\
           {
              NewHuman {
                id
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            rename_schema(parse(ISS.basic_schema), {'Human': 'NewHuman'})
        )
        renamed_query_string = dedent('''\
            {
              Human {
                id
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))

    def test_rename_named_query(self):
        query_string = dedent('''\
            query HumanIdQuery {
              NewHuman {
                id
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            rename_schema(parse(ISS.basic_schema), {'Human': 'NewHuman'})
        )
        renamed_query_string = dedent('''\
            query HumanIdQuery {
              Human {
                id
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))
    """
    def test_rename_nested_query(self):
        query_string = dedent('''\
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
        renamed_query = rename_query(
            parse(query_string),
            rename_schema(parse(ISS.basic_schema), {'Human': 'NewHuman'})
        )
        renamed_query_string = dedent('''\
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
        self.assertEqual(renamed_query_string, print_ast(renamed_query))
    """

    def test_inline_fragment(self):
        query_string = dedent('''\
            {
              NewCharacter {
                id
                ... on NewHuman {
                  age
                }
              }
            }
        ''')
        renamed_query = rename_query(
            parse(query_string),
            rename_schema(parse(ISS.multiple_interfaces_schema),
                          {'Human': 'NewHuman', 'Character': 'NewCharacter'}
            )
        )
        renamed_query_string = dedent('''\
            {
              Character {
                id
                ... on Human {
                  age
                }
              }
            }
        ''')
        self.assertEqual(renamed_query_string, print_ast(renamed_query))
    """
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
        self.assertEqual(renamed_query_string, print_ast(renamed_query))"""

    def test_invalid_type_not_in_schema(self):
        query_string = dedent('''\
           {
              RandomType {
                name
              }
            }
        ''')
        rename_query(
            parse(query_string),
            rename_schema(parse(ISS.basic_schema), {'Human': 'NewHuman'})
        )

    def test_invalid_field_not_in_schema(self):
        query_string = dedent('''\
           {
              NewHuman {
                name
              }
            }
        ''')
        rename_query(
            parse(query_string),
            rename_schema(parse(ISS.basic_schema), {'Human': 'NewHuman'})
        )

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
        with self.assertRaises(GraphQLValidationError):
            rename_query(parse(query_string), rename_schema(parse(ISS.basic_schema), {}))

    def test_invalid_fragment(self):
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
              id
            }
        ''')
        with self.assertRaises(GraphQLValidationError):
            rename_query(parse(query_string), rename_schema(parse(ISS.basic_schema), {}))

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
        with self.assertRaises(GraphQLValidationError):
            rename_query(parse(query_string), rename_schema(parse(ISS.basic_schema), {}))
