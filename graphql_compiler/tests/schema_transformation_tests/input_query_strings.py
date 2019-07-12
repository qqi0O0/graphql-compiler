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
