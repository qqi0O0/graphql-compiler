from collections import namedtuple

from graphql import build_ast_schema
from graphql.language import ast as ast_types
from graphql.language.visitor import TypeInfoVisitor, Visitor, visit
from graphql.type.definition import GraphQLList, GraphQLNonNull, GraphQLUnionType
from graphql.utils.type_info import TypeInfo


# Break down into two steps, one for splitting the tree with minimum modifications (just adding
# the type on the outermost scope) and keeping track of connecting edge information, one for
# modifying the split tree with appropriate @filter and @output directives


QueryConnection = namedtuple(
    'QueryConnection', (
        'sink_query_node',  # QueryNode namedtuple
        'source_field',  # Field
        'sink_field',  # Field
    )
)
# Making the connect be source/sink rather than parent/child makes it much easier to reroot
# the tree if needed -- just pick a different QueryConnection amoung child_query_connections
# to replace parent_query_connection


class QueryNode(object):
    def __init__(self, query_ast):  # schema_id?
        self.query_ast = query_ast
        self.parent_query_connection = None
        self.child_query_connections = []

        # where to keep track of what output columns are actual user outputs?

    # Represent as a completely bidirectional, unrooted tree?
    # Seems excessive, default to a normally rooted tree, but make it not impossible to change
    # the rooting if desired.
    # @output directives can be attached before order of the tree is known, but @filter and
    # information on what column is put into what filter must come after the order of the tree
    # is known


def split_query(query_ast, merged_schema_descriptor):
    """Split input query AST into a tree of QueryNodes targeting each individual schema.

    Args:
        query_ast: Document, representing a GraphQL query to split
        merged_schema_descriptor: MergedSchemaDescriptor namedtuple, containing:
                                  schema_ast: Document representing the merged schema
                                  type_name_to_schema_id: Dict[str, str], mapping name of each
                                                          type to the id of the schema it came
                                                          from

    Returns:
        QueryNode, the root of the tree of QueryNodes. Each node contains an AST
        representing a part of the overall query, targeting a specific schema
    """
    base_query_node = QueryNode(query_ast)
    
    type_info = TypeInfo(build_ast_schema(merged_schema_descriptor.schema_ast))

    # If schema directives are not swallowed, type_info is all that's needed to detect and
    # address stitching fields
    # However, before this issue is fixed, it's necessary to use additional information from
    # preprocessing the schema AST
    # want: map of (type name, edge field name) to (source field name, sink field name)
    edge_to_stitch_fields = {}
    for type_definition in merged_schema_descriptor.schema_ast.definitions:
        if isinstance(type_definition, (
            ast_types.ObjectTypeDefinition, ast_types.InterfaceTypeDefinition
        )):
            for field_definition in type_definition.fields:
                stitch_directive_arguments = None
                for directive_definition in field_definition.directives:
                    if directive_definition.name.value == u'stitch':
                        stitch_directive_arguments = directive_definition.arguments
                if stitch_directive_arguments is not None:
                    # validation of form of input?
                    source_field_name = stitch_directive_arguments[0].value.value
                    sink_field_name = stitch_directive_arguments[1].value.value
                    edge = (type_definition.name.value, field_definition.name.value)
                    edge_to_stitch_fields[edge] = (source_field_name, sink_field_name)

    # Construct full tree of QueryNodes in a dfs pattern
    query_nodes_to_visit = [base_query_node]
    while len(query_nodes_to_visit) > 0:
        current_node_to_visit = query_nodes_to_visit.pop()
        # visit will break down the ast included inside current_node_to_visit into potentially
        # multiple query nodes, all added to child_query_nodes list of current_node_to_visit
        split_query_visitor = SplitQueryVisitor(type_info, edge_to_stitch_fields, 
                                                current_node_to_visit)
        visitor = TypeInfoVisitor(type_info, split_query_visitor)
        visit(current_node_to_visit.query_ast, visitor)
        query_nodes_to_visit.extend(
            child_query_connection.sink_query_node
            for child_query_connection in current_node_to_visit.child_query_connections
        )

    return base_query_node


class SplitQueryVisitor(Visitor):
    """Prune branches of AST and build tree of QueryNodes while visiting."""
    # Only visit and prune first level? Stop upon creating a new query node in each branch?
    # Then recursively visit each child branch again? I like it.
    def __init__(self, type_info, edge_to_stitch_fields, base_query_node):
        """
        Args:
            type_info: TypeInfo
            edge_to_stitch_fields: Dict[Tuple[str, str], Tuple[str, str]], mapping 
                                   (name of type, name of field representing the edge) to
                                   (source field name, sink field name)
            base_query_node: QueryNode, its query_ast and child_query_connections are modified
        """
        self.type_info = type_info
        self.edge_to_stitch_fields = edge_to_stitch_fields
        self.base_query_node = base_query_node

    def enter_Field(self, node, key, parent, path, ancestors):
        """Check for split at the current field.

        If there is a new split at this field as clued by a @stitch directive, a new Document
        will be created containing the current branch, with a new field 

        If there is a new split as clued by a @stitch directive, a new Document will be created
        containing the current branch, with some modifications at the root. The new Document
        will be wrapped in a QueryNode, and added to query_nodes_stack. The rest of the branch
        will not be visited.
        """
        # source will be used to refer to the type that has the current field
        # sink will be used to refer to the type that the current field goes to
        # TODO: use parent/child here?
        source_type = self.type_info.get_parent_type()  # GraphQLObjectType or GraphQLInterfaceType

        # Get whether or not there is a stitch here, based on name of the type and field
        # This is only necessary because schemas do not keep track of schema directives
        # correctly. Once that is fixed, TypeInfo should be all that's needed.
        source_type_name = source_type.name
        edge_field_name = node.name.value
        edge_field_descriptor = (source_type_name, edge_field_name)

        if not edge_field_descriptor in self.edge_to_stitch_fields:  # no stitch at this field
            return

        source_field_name, sink_field_name = self.edge_to_stitch_fields[edge_field_descriptor]

        # Get root vertex field name and selection set of the cut off branch of the AST
        sink_type = self.type_info.get_type()  # GraphQLType, may be wrapped in List or NonNull
        # assert that sink_type is a GraphQLList?
        # NOTE: how does NonNull for sink_type affect anything?
        while isinstance(sink_type, (GraphQLList, GraphQLNonNull)):
            sink_type = sink_type.of_type
        sink_type_name = sink_type.name
        sink_selection_set = node.selection_set

        # Adjust for type coercion due to the sink_type being an interface or union
        if (
            len(sink_selection_set.selections) == 1 and
            isinstance(sink_selection_set.selections[0], ast_types.InlineFragment)
        ):
            type_coercion_inline_fragment = sink_selection_set.selections[0]
            sink_type_name = type_coercion_inline_fragment.type_condition.name.value
            sink_selection_set = type_coercion_inline_fragment.selection_set

        # Check for existing field in child
        sink_field = self._try_get_field_with_name(sink_selection_set.selections, sink_field_name)
        if sink_field is None:
            # Add new field to child's selection set
            sink_field = ast_types.Field(name=ast_types.Name(value=sink_field_name))
            sink_selection_set.selections.insert(0, sink_field)
        # Create new AST for the pruned branch
        branch_query_ast = ast_types.Document(
            definitions=[
                ast_types.OperationDefinition(
                    operation='query',
                    selection_set=ast_types.SelectionSet(
                        selections=[
                            ast_types.Field(
                                name=ast_types.Name(value=sink_type_name),
                                selection_set=sink_selection_set,
                            )
                        ]
                    )
                )
            ]
        )

        # Create new QueryNode for pruned branch
        child_query_node = QueryNode(branch_query_ast)


        # Check for existing field in source (self)
        source_field = self._try_get_field_with_name(parent, source_field_name)
        if source_field is None:
            # Change stump field to source field
            # TODO: deal with preexisting directives
            node.name.value = source_field_name
            assert(node.alias is None)
            assert(node.arguments is None or node.arguments==[])
            assert(node.directives is None or node.directives==[])
            node.selection_set = []
            source_field = node
        else:
            # Remove stump field
            parent[key] = None

        # Create QueryConnections
        # Figure out terminology between source/sink and parent/child
        new_query_connection_from_source = QueryConnection(
            sink_query_node=child_query_node,
            source_field=source_field,
            sink_field=sink_field,
        )
        new_query_connection_from_sink = QueryConnection(
            sink_query_node=self.base_query_node,
            source_field=sink_field,  # Remarkably confusing
            sink_field=source_field,
        )
        # NOTE: make sure sink_field and node are correct even if those leaves already existed

        # Add QueryConnection to parent and child
        self.base_query_node.child_query_connections.append(new_query_connection_from_source)
        child_query_node.parent_query_connection = new_query_connection_from_sink

        # visit interprets return value of False as skip visiting branch
        # leave_Field will not be called on this field
        return False

    def _try_get_field_with_name(self, selections, target_field_name):
        """Return the Field with the desired name from the list, if found.

        Args:
            selections: List[Field or InlineFragment], as found in the selections attribute
                        of a SelectionSet
            target_field_name: str, name of the field we're looking for

        Returns:
            Field, an element in selections of the correct name, or None if no such field exists
        """
        for selection in selections:
            if isinstance(selection, ast_types.Field):
                if selection.name.value == target_field_name:
                    return selection
        return None



# Ok, conclusion:
# Keep track of set of user output columns, update parent set with union when joining
# Delete all non-user-output columns at the very end
# Columns have globally unique names
# Each merging edge keeps track of names of parent and child columns, as well as any additional
#   information (is optional join, etc)
# When merging, both columns are kept
# Fail if merging with both ends being user output?
