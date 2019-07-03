from graphql.language.visitor import Visitor, visit


class SchemaError(Exception):
    pass


class SchemaData(object):
    def __init__(self):
        self.query_type = None
        self.scalars = set()
        self.directives = set()
        self.has_extension = False


class GetSchemaDataVisitor(Visitor):
    """Gather information about the schema before making any transforms."""
    def __init__(self):
        self.schema_data = SchemaData()

    def enter_TypeExtensionDefinition(self, node, *args):
        self.schema_data.has_extension = True

    def enter_OperationTypeDefinition(self, node, *args):
        if node.operation == 'query':  # might add mutation and subscription options
            self.schema_data.query_type = node.type.name.value

    def enter_ScalarTypeDefinition(self, node, *args):
        self.schema_data.scalars.add(node.name.value)

    def enter_DirectiveDefinition(self, node, *args):
        # NOTE: currently we don't check if the definitions of the directives agree.
        # Any directive that comes after one of the same one is simply erased
        self.schema_data.directives.add(node.name.value)


def get_schema_data(ast):
    """Get schema data of input ast.

    Args:
        ast: Document

    Return:
        SchemaData
    """
    # NOTE: currently we're calling this whenever needed, rather than passing the computed
    # schema_data around. This can be optimized if needed
    get_schema_data_visitor = GetSchemaDataVisitor()
    visit(ast, get_schema_data_visitor)
    return get_schema_data_visitor.schema_data
