from textwrap import dedent
import unittest

from graphql import parse, print_ast

from ...schema_transformation.restrict_schema import restrict_schema


class TestRestrictSchema(unittest.TestCase):
    def test_simple(self):
        schema_str = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              name: String
              pet: Pet
              friend: Person
            }

            type Pet {
              name: String
              owner: Person
              friend: Pet
            }

            type SchemaQuery {
              Person: Person
              Pet: Pet
            }
        ''')
        schema_ast = parse(schema_str)
        restricted_schema_ast = restrict_schema(schema_ast, {'Person'})
        print(print_ast(schema_ast))
        print()
        print(print_ast(restricted_schema_ast))
