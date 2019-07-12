# Copyright 2019-present Kensho Technologies, LLC.
from textwrap import dedent


class InputQueryStrings(object):
    basic_named_query = dedent('''\
        query HumandIdQuery {
          Human {
            id
          }
        }
    ''')

    basic_unnamed_query = dedent('''\
       {
          Human {
            id
          }
        }
    ''')

    nested_query = dedent('''\
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

    alias_query = dedent('''\
        query FetchLukeAliased {
          luke: Human(id: "1000") {
            name
          }
        }
    ''')

    multiple_alias_query = dedent('''\
        query FetchLukeAndLeiaAliased {
          luke: Human(id: "1000") {
            name
          }
          leia: Human(id: "1003") {
            name
          }
        }
    ''')
