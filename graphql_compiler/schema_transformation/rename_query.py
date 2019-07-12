# Copyright 2019-present Kensho Technologies, LLC.
from copy import deepcopy

from graphql import parse
from graphql.language.visitor import Visitor, visit
from graphql.language.printer import print_ast


def rename_query(ast, renamings):
    """Translate all types and entry point fields (fields of query type) using renamings.

    Most fields (fields of types other than the query type) will not be renamed. Any type
    or field that does not appear in renamings will be unchanged.
    Roughly speaking, rename_query renames the same elements as rename_schema.

    This may be used in conjunction with rename_schema. For instance, one may pass in a query
    written in the renamed schema's types and fields, as well as reverse_name_map of the
    renamed schema, to receive the same query written in the original schema's types and fields.

    Args:
        ast: Document, representing a valid query; not modified by this function
        renamings: Dict[str, str], mapping original types/query type field names as appearing
                   in the query to renamed names. Type or query type field names not appearing
                   in the dict will be unchanged

    Returns:
        Document, a new AST representing the renamed query
    """
    ast = deepcopy(ast)

    # NOTE: unlike with schemas, there's no such thing as build_ast_query or anything like that
    # to check that the structure of the query fits expectations.
    # Any need to check that? Or leave it be the responsibility of the user to ensure that
    # they're putting in a valid query AST?

    visitor = RenameQueryVisitor(renamings)
    visit(ast, visitor)

    return print_ast(ast)


class RenameQueryVisitor(Visitor):
    def __init__(self, renamings):
        """Create a visitor for renaming types and entry point fields in a query AST.

        Args:
            renamings: Dict[str, str], mapping from o
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
    

    # for renaming root fields, need to 1. check that we're under an OperationDefinition with
    # operation equal to query, and 2. we're in the first level of SelectionSet

    # for renaming types, just renamed all NamedTypes that appear in the dict.
    # scalar types cannot appear as NamedType in a query I believe?
