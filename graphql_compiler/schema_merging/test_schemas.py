from textwrap import dedent


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

    type Human implements Character {
      name: String
    }

    type SchemaQuery {
      Character: Character
      Human: Human
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
      name: String
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
      HumanOrDroid: HumanOrDroid
    }
''')

list_schema = dedent('''\
    schema {
      query: SchemaQuery
    }

    type Droid implements Character {
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

directives_schema = dedent('''\
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
      name: String
      birthday: Date
    }

    type Giraffe implements Character {
      height: Height
    }

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
      name: String
      birthday: Date
    }

    type Giraffe implements Character {
      height: Height
    }

    type SchemaQuery {
      Human: Human
      Giraffe: Giraffe
    }
''')
