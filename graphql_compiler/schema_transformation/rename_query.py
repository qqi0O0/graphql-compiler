# Copyright 2019-present Kensho Technologies, LLC.
from copy import deepcopy

from graphql.language import ast as ast_types
from graphql.language.visitor import Visitor, visit

from .utils import QueryStructureError


# TODO:
# Validation happens after all AST to AST transformations, and issues with the input AST in
# the renaming step can interact poorly with the validation step, causing unhelpful errors
# (e.g. if query starts with a type coercion, the error user sees would be a name error due to
# a type not being renamed, not the root cause -- starting with a type coercion)
# How to validate? How much to validate?
# Alternatively, behave correctly in edge cases, so that any error present in the input will
# be intactly present in the output, and will be caught at the validation stage?


def rename_query(ast, renamings):
    """Translate all types and root fields (fields of query type) using renamings.

    Most fields (fields of types other than the query type) will not be renamed. Any type
    or field that does not appear in renamings will be unchanged.
    Roughly speaking, rename_query renames the same elements as rename_schema.

    Args:
        ast: Document, representing a valid query. It is assumed to have passed GraphQL's
             builtin validation, through validate(schema, ast). Not modified by this function
        renamings: Dict[str, str], mapping original types/query type field names as appearing
                   in the query to renamed names. Type or query type field names not appearing
                   in the dict will be unchanged

    Returns:
        Document, a new AST representing the renamed query

    Raises:
        - QueryStrutureError if the ast does not have the expected form; in particular, if the
          AST contains 
    """
    # NOTE: There is a whole section 'validation' in graphql-core that takes in a schema and a
    # query ast, and checks whether the query is valid. This code assumes this validation
    # step has been done on the input AST.
    if len(ast.definitions) > 1:
        raise QueryStructureError(u'Either multiple queries were included, or fragments were '
                                  u'defined.')

    query_definition = ast.definitions[0]

    for selection in query_definition.selection_set.selections:
        if not isinstance(selection, ast_types.Field):
            raise QueryStructureError(u'Each root selections must be "Field", '
                                      u'not "{}"'.format(type(selection).__name__))

    ast = deepcopy(ast)

    visitor = RenameQueryVisitor(renamings)
    visit(ast, visitor)

    return ast


class RenameQueryVisitor(Visitor):
    def __init__(self, renamings):
        """Create a visitor for renaming types and fields of the query type in a query AST.

        Args:
            renamings: Dict[str, str], mapping from original type name to renamed type name.
                       Any name not in the dict will be unchanged
        """
        self.renamings = renamings
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

    def enter_SelectionSet(self, node, *args):
        """Record that we entered another nested level of selections."""
        self.selection_set_level += 1

    def leave_SelectionSet(self, node, *args):
        """Record that we left a level of selections."""
        self.selection_set_level -= 1

    def enter_Field(self, node, *args):
        """Rename entry point fields, aka fields of the query type."""
        # For a Field to be a field of the query type, it needs to be:
        # - The first level of selections (fields in more nested selections are normal fields,
        # and should not be modified)
        # As a query may not start with type coercion (aka inline fragment), and
        # FragmentDefinition is not allowed, an element in the first level of selection set
        # in a definition must be a field of the query type
        if self.selection_set_level == 1:
            self._rename_name(node.name)
