# Copyright 2019-present Kensho Technologies, LLC.
from graphql import parse
from graphql.language.visitor import Visitor, visit
from graphql.langiage.printer import print_ast


# Call this rename_query instead? Its effects are similar to rename_schema, it doesn't need to
# take in a 'reverse_name_map' but just any 'remaings'. It's just that one use case is for
# transforming queries with renamed types back into originals.
# It should just take in a name_map, not a renamed_schema

# One issue: rename_schema and merge_schema take in AST(s) and output some kind of descriptor
# that contains a dictionary and an AST. This takes in a string and outputs a string, even though
# it's named the same way as rename_schema




def rename_query(query_string, renamings):
    """Translate all types and entry point fields (fields of query type) using renamings.

    Most fields (fields of types other than the query type) will not be renamed. Any type
    or field that does not appear in renamings will be unchanged.
    Roughly speaking, rename_query renames the same elements as rename_schema.

    This may be used in conjunction with rename_schema. For instance, one may pass in a query
    written in the renamed schema's types and fields, as well as reverse_name_map of the
    renamed schema, to receive the same query written in the original schema's types and fields.

    Args:
        query_string: str
        renamings: Dict[str, str], 
        renamed_schema: RenamedSchema, namedtuple containing the ast of the renamed schema, and
                        a map of renamed names to original names

    Returns:
        query string where type names are demangled
    """
    ast = parse(query_string)
    reverse_name_map = renamed_schema.reverse_name_map

    visitor = DemangleQueryVisitor(reverse_name_map)
    visit(ast, visitor)

    return print_ast(ast)


class DemangleQueryVisitor(Visitor):
    def __init__(self, name_map):
        """
        """
        pass
    # some fields are not translated, such as alias or various non-root field names
    # how to tell?

    # Want to rename two things: the first level selection set field names (root fields)
    # and NamedTypes (e.g. in fragments)
    # Should do those in two steps
    # TODO
    # First step doesn't need visitor. Just iterate over selection set like with dedup
    # Second step uses very simple visitor that transforms all NamedTypes that are not scalars
    # or builtins?
    

    # for demangling root fields, need to 1. check that we're under an OperationDefinition with
    # operation equal to query, and 2. we're in the first level of SelectionSet

    # for demangling types, just demangle all NamedTypes that appear in the dict.
    # scalar types cannot appear as NamedType in a query I believe?
