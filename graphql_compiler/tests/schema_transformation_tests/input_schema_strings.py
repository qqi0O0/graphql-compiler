# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent


class InputSchemaStrings(object):
    basic_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type Human {
          id: String
        }

        type SchemaQuery {
          Human: Human
        }
    ''')

    multiple_types_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type Human {
          name: String
        }

        type Droid {
          id: String
        }

        type Dog {
          nickname: String
        }

        type SchemaQuery {
          Human: Human
          Droid: Droid
          Dog: Dog
        }
    ''')

    enum_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type Droid {
          height: Height
        }

        type SchemaQuery {
          Droid: Droid
        }

        enum Height {
          TALL
          SHORT
        }
    ''')

    interface_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        interface Character {
          id: String
        }

        type Kid implements Character {
          id: String
        }

        type SchemaQuery {
          Character: Character
          Kid: Kid
        }
    ''')

    interfaces_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        interface Character {
          id: String
        }

        interface Creature {
          age: Int
        }

        type Human implements Character, Creature {
          id: String
          age: Int
        }

        type SchemaQuery {
          Character: Character
          Creature: Creature
          Human: Human
        }
    ''')

    scalar_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type Human {
          birthday: Date
        }

        scalar Date

        type SchemaQuery {
          Human: Human
        }
    ''')

    union_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type Human {
          id: String
        }

        type Droid {
          id: String
        }

        union HumanOrDroid = Human | Droid

        type SchemaQuery {
          Human: Human
          Droid: Droid
        }
    ''')

    list_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type Droid implements Character {
          id: String
          heights: [Height]
          dates: [Date]
          friends: [Droid]
          enemies: [Character]
        }

        type SchemaQuery {
          Droid: [Droid]
        }

        scalar Date

        interface Character {
          id: String
        }

        enum Height {
          TALL
          SHORT
        }
    ''')

    non_null_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type Dog {
          id: String!
          friend: Dog!
        }

        type SchemaQuery {
          Dog: Dog!
        }
    ''')

    directive_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type Human {
          id: String
        }

        type Droid {
          id: String
          friend: Human @stitch(source_field: "id", sink_field: "id")
        }

        directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

        type SchemaQuery {
          Human: Human
          Droid: Droid
        }
    ''')

    various_types_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        scalar Date

        enum Height {
          TALL
          SHORT
        }

        interface Character {
          id: String
        }

        type Human implements Character {
          id: String
          name: String
          birthday: Date
        }

        type Giraffe implements Character {
          id: String
          height: Height
        }

        directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

        type SchemaQuery {
          Human: Human
          Giraffe: Giraffe
        }
    ''')

    multiple_scalars_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        scalar Date

        scalar DateTime

        scalar Decimal

        enum Height {
          TALL
          SHORT
        }

        interface Character {
          id: String
        }

        type Human implements Character {
          id: String
          name: String
          birthday: Date
        }

        type Giraffe implements Character {
          id: String
          height: Height
        }

        type SchemaQuery {
          Human: Human
          Giraffe: Giraffe
        }
    ''')

    invalid_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type SchemaQuery {
          Human: Human
        }
    ''')

    double_underscore_schema = dedent('''\
        schema {
          query: SchemaQuery
        }

        type SchemaQuery {
          __Human: __Human
        }

        type __Human {
          id: String
        }
    ''')
