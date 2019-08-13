from graphql import TypeInfo

from graphql.language.visit import visit, Visitor, TypeInfoVisitor


def restrict_schema(schema_ast, types_to_keep):
    """Return new AST that only contains types_to_keep and edges between such types and scalars.

    schema_ast: Document representing schema
    types_to_keep: Set[str], types with such names are kept
    """
    # What do with types with 0 fields? Warn user? AST doesn't care so maybe just ok
    # Always keep query type


class RestrictSchemaVisitor(Visitor):
    def __init__(self, type_info, types_to_keep, query_type, scalars):
        """"""
        self.type_info = type_info
        self.types_to_keep = types_to_keep
        self.query_type = query_type
        self.scalars = scalars

    def enter_():
        pass
