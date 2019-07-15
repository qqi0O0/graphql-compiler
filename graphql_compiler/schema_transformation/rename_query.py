# Copyright 2019-present Kensho Technologies, LLC.
from copy import deepcopy

from graphql import parse
from graphql.language.printer import print_ast
from graphql.language.visitor import Visitor, visit


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
    # Question: Allow document to represent not 1, but any number of queries? There is no
    # change to the code.
    # Question: Disallow fragments, and raise error if we see one?
    # Question: How much do we check the validity of the input ast?

    # NOTE: There is a whole section 'validation' in graphql-core that takes in a schema and a
    # query ast, and checks whether the query is valid. This code currently does not check for
    # validity of the input or remaing at all, but assumes that the input is a valid query ast
    # and the renamings dict is so that the output is a valid query. If it is not, the
    # output may be strange or unexpected, but no errors will be raised.
    ast = deepcopy(ast)

    visitor = RenameQueryVisitor(renamings)
    visit(ast, visitor)

    return ast


class RenameQueryVisitor(Visitor):
    def __init__(self, renamings):
        """Create a visitor for renaming types and entry point fields in a query AST.

        Args:
            renamings: Dict[str, str], mapping from original type name to renamed type name.
                       Any name not in the dict will be unchanged
        """
        self.renamings = renamings
        self.in_query = False
        self.selection_set_level = 0

    def _rename_name(self, node):
        """Rename the value of the node as according to renamings.

        Modifies node.

        Args:
            node: type Name, an AST Node object that describes the name of its parent node in
                  the AST
        """
        name_string = node.value
        new_name_string = self.renamings.get(name_string, name_string)  # Default use original
        node.value = new_name_string

    def enter_NamedType(self, node, *args):
        """Rename name of node."""
        # NamedType nodes describe types in the schema and should always be renamed
        # They may appear in, for example, InlineFragment
        self._rename_name(node.name)

    def enter_OperationDefinition(self, node, *args):
        """If node's operation is query, record that we entered a query definition."""
        if node.operation == 'query':
            self.in_query = True

    def leave_OperationDefinition(self, node, *args):
        """If node's operation is query, record that we left a query definition."""
        if node.operation == 'query':
            self.in_query = False

    def enter_SelectionSet(self, node, *args):
        """Record that we entered another nested level of selections."""
        self.selection_set_level += 1

    def leave_SelectionSet(self, node, *args):
        """Record that we left a level of selections."""
        self.selection_set_level -= 1

    def enter_Field(self, node, *args):
        """Rename entry point fields, aka fields of the query type."""
        # For a Field to be a field of the query type, it needs to be:
        # - Under the query operation definition (if a Field is not under the query operation
        # definition, it may be a part of a Fragment definition)
        # - The first level of selections (fields in more nested selections are normal fields,
        # and should not be modified)
        # As a query may not start with type coercion (aka inline fragment), an element in the
        # first level of selection set must be a field of the query type
        if self.in_query and self.selection_set_level == 1:
            self._rename_name(node.name)
