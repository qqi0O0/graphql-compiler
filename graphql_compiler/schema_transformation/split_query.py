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


class QueryNode(object):
    def __init__(self, query_ast):  # schema_id?
        self.query_ast = query_ast
        self.parent_query_connection = None
        self.child_query_connections = []

    # Represent as a completely bidirectional, unrooted tree?
    # Seems excessive, default to a normally rooted tree, but make it not impossible to change
    # the rooting if desired.
    # Current way of expressing parent and child connections seems like a pain to reverse,
    # but maybe it's ok
    # A single field called 'neighbors' or something
    # @output directives can be attached before order of the tree is known, but @filter and
    # information on what column is put into what filter must come after the order of the tree
    # is known
    # How would one express edge directions?


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

        If there is a new split as clued by a @stitch directive, a new Document will be created
        containing the current branch, with some modifications at the root. The new Document
        will be wrapped in a QueryNode, and added to query_nodes_stack. The rest of the branch
        will not be visited.
        """
        source_type = self.type_info.get_parent_type()  # GraphQLObjectType or GraphQLInterfaceType

        source_type_name = source_type.name
        edge_field_name = node.name.value
        # Get whether or not there is a stitch here, based on source_name and current field name
        edge_field_descriptor = (source_type_name, edge_field_name)

        if not edge_field_descriptor in self.edge_to_stitch_fields:
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

        # Add new field to child's selection set
        # TODO: don't add if this field already exists
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

        # Create QueryConnection
        new_query_connection = QueryConnection(
            parent_query_node = self.base_query_node,
            parent_field = node,  # NOTE: changes if this leaf field already exists
            child_query_node = child_query_node,
            child_field = sink_field  # NOTE: changes if this field already exists
        )

        # Add QueryConnection to parent and child
        self.base_query_node.child_query_connections.append(new_query_connection)
        child_query_node.parent_query_connection = new_query_connection

        # Change stump field to a leaf node
        # TODO: if this leaf node already exists
        # TODO: deal with preexisting directives
        node.name.value = source_field_name
        assert(node.alias is None)
        assert(node.arguments is None or node.arguments==[])
        assert(node.directives is None or node.directives==[])
        node.selection_set = None

        # visit interprets return value of False as skip visiting branch
        # leave_Field will not be called on this field
        return False



# Ok, conclusion:
# Keep track of set of user output columns, update parent set with union when joining
# Delete all non-user-output columns at the very end
# Columns have globally unique names
# Each merging edge keeps track of names of parent and child columns, as well as any additional
#   information (is optional join, etc)
# When merging, both columns are kept
# Fail if merging with both ends being user output?


class QueryNode(object):  # rename to QueryPlanNode?
    """A tree node wrapping around a query AST.

    Used to represent a part of a split query. The tree as whole represents dependencies among
    the split query pieces. If node A is a child of node B, then the execution of the query
    piece in node A is dependent on some outputs of the query piece in node B.
    """
    # Also need to deal with directives like @fold and @optional, the code needs to be able
    # to deal with these additions
    def __init__(self, query_ast, schema_id, input_filter_name, parent_join_descriptor,
                 parent_node):
        """Create a QueryNode representing a part of a split query.

        Args:
            query_ast: Document, representing a piece of the split query
            schema_id: str, identifying the schema that this query piece targets
            input_filter_name: str, name of the local variable X used in
                               @filter(op_name: "in_collection", value: ["$X"]) of the field
                               used to stitch together this query result with its parent
            parent_join_decriptor: JoinDescriptor, describing how this query result is to be
                                   combined with the result of its parent
            parent_node: QueryNode, the query piece whose output the current query piece depends
                         on
        """
        self.query_ast = query_ast
        self.schema_id = schema_id
        self.input_filter_name = input_filter_name
        self.parent_join_descriptor = parent_join_descriptor
        self.parent_node = parent_node
        self.child_query_nodes = []
        # List[QueryNode], queries that depend on the current query's outputs
        self.user_outputs = set()
        # Set[str], names of actual user output columns (as opposed to columns used internally)

    # Possibly define operations for dfs and bfs
    # Possibly contain a field for results


class QueryResultNode(object):
    def __init__(self, raw_result, parent_join_descriptor, user_outputs, parent_result_node,
                 child_result_nodes):
        """Create a wrapper around a piece of query result, with joining information.

        Args:
            raw_result: List[Dict[str, any]], representing a table of query results
            parent_join_descriptor: JoinDescriptor, describing how this query result is to be
                                    combined with the parent result
            user_outputs: Set[str], names of columns of raw_results that are actual user
                          outputs and not used for internal combining
            parent_result: QueryResultNode, the parent of the current result
            child_result_nodes: List[QueryResultNode], the children of the current result
        """
        # Does order of joining edges matter?


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
    # No validation for now
    type_name_to_schema_id = merged_schema_descriptor.type_name_to_schema_id

    # Get schema of the base node
    root_vertex_field = query_ast.definitions[0].selection_set.selections[0].name.value
    base_schema_id = type_name_to_schema_id[root_vertex_field]  # same name as type
    base_query_node = QueryNode(query_ast, base_schema_id)

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
                                                current_node_to_visit, type_name_to_schema_id)
        visitor = TypeInfoVisitor(type_info, split_query_visitor)
        visit(current_node_to_visit.query_ast, visitor)
        query_nodes_to_visit.extend(current_node_to_visit.child_query_nodes)

    return base_query_node


class SplitQueryVisitor(Visitor):
    """Prune branches of AST and build tree of QueryNodes while visiting."""
    # Only visit and prune first level? Stop upon creating a new query node in each branch?
    # Then recursively visit each child branch again? I like it.
    def __init__(self, type_info, edge_to_stitch_fields, base_query_node, type_name_to_schema_id):
        """
        Args:
            type_info: TypeInfo
            edge_to_stitch_fields: Dict[Tuple[str, str], Tuple[str, str]], mapping 
                                   (name of type, name of field representing the edge) to
                                   (source field name, sink field name)
            base_query_node: QueryNode, its query_ast and child_query_nodes are modified
            type_name_to_schema_id: Dict[str, str]
        """
        self.type_info = type_info
        self.edge_to_stitch_fields = edge_to_stitch_fields
        self.base_query_node = base_query_node
        self.type_name_to_schema_id = type_name_to_schema_id
        self._input_parameter_count = -1

    def enter_Field(self, node, key, parent, path, ancestors):
        """Check for split at the current field.

        If there is a new split as clued by a @stitch directive, a new Document will be created
        containing the current branch, with some modifications at the root. The new Document
        will be wrapped in a QueryNode, and added to query_nodes_stack. The rest of the branch
        will not be visited.
        """
        source_type = self.type_info.get_parent_type()  # GraphQLObjectType or GraphQLInterfaceType

        source_type_name = source_type.name
        edge_field_name = node.name.value
        # Get whether or not there is a stitch here, based on source_name and current field name
        edge_field_descriptor = (source_type_name, edge_field_name)

        if not edge_field_descriptor in self.edge_to_stitch_fields:
            return

        source_field_name, sink_field_name = self.edge_to_stitch_fields[edge_field_descriptor]

        # Get root vertex field name and selection set of the cut off branch of the AST
        sink_type = self.type_info.get_type()  # GraphQLType, may be wrapped in List or NonNull
        # assert that sink_type is a GraphQLList?
        # NOTE: how does NonNull for sink_type affect anything?
        while isinstance(sink_type, (GraphQLList, GraphQLNonNull)):
            sink_type = sink_type.of_type
        sink_type_name = sink_type.name
        sink_schema_id = self.type_name_to_schema_id[sink_type_name]
        sink_selection_set = node.selection_set

        # Adjust for type coercion due to the sink_type being an interface or union
        if (
            len(sink_selection_set.selections) == 1 and
            isinstance(sink_selection_set.selections[0], ast_types.InlineFragment)
        ):
            type_coercion_inline_fragment = sink_selection_set.selections[0]
            sink_type_name = type_coercion_inline_fragment.type_condition.name.value
            sink_selection_set = type_coercion_inline_fragment.selection_set

        # Selection set needs to be padded with an initial field with filter
        # unless that initial field already exists
        # TODO: rename input_parameter_name to something more fitting
        input_parameter_name = self._get_input_parameter_name()
        self.attach_input_filter_directive(
            sink_selection_set, sink_field_name, input_parameter_name
        )

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

        # Create new QueryNode for pruned branch, add to parent
        branch_query_node = QueryNode(branch_query_ast, sink_schema_id, input_parameter_name,
                                      self.base_query_node)
        self.base_query_node.child_query_nodes.append(branch_query_node)

        # Change stump field to a leaf node with the correct output
        node.name.value = source_field_name
        assert(node.alias is None)
        assert(node.arguments is None or node.arguments==[])
        assert(node.directives is None or node.directives==[])
        node.directives = [
            ast_types.Directive(
                name=ast_types.Name(value=u'output'),
                arguments=[
                    ast_types.Argument(
                        name=ast_types.Name(value=u'out_name'),
                        value=ast_types.StringValue(value=input_parameter_name)
                    )
                ]
            )
        ]
        node.selection_set = None

        # visit interprets return value of False as skip visiting branch
        # leave_Field will not be called on this field
        return False

    def _get_input_parameter_name(self):
        # NOTE: different fields must have unique output names when used for stitching, for
        # example, if there are two stitchs happening, and the stitched field is called the
        # same thing in both, there must be no confusion. type + field is enough? what if
        # there are multiple fields of the same type? something like 
        # Human {
        #   out_Human_Person {
        #     name
        #   }
        #   friend {
        #     out_Human_Person {
        #       name
        #     }
        #   }
        # }
        # TODO: need to avoid such conflicts
        # TODO: need to avoid conflicts with existing @output directives
        self._input_parameter_count += 1
        return u'__input_parameter_' + str(self._input_parameter_count)

    def attach_input_filter_directive(self, selection_set, sink_field_name, input_parameter_name):
        """Modifies selection, used on the root of a new QueryNode."""
        directives = [
            ast_types.Directive(
                name=ast_types.Name(value=u'filter'),
                arguments=[
                    ast_types.Argument(
                        name=ast_types.Name(value=u'op_name'),
                        value=ast_types.StringValue(
                            value=u'in_collection'
                        )
                    ),
                    ast_types.Argument(
                        name=ast_types.Name(value=u'value'),
                        value=ast_types.ListValue(
                            values=[ast_types.StringValue(value=(u'$' + input_parameter_name))]
                        )
                    )
                ]
            ),
            ast_types.Directive(
                name=ast_types.Name(value=u'output'),
                arguments=[
                    ast_types.Argument(
                        name=ast_types.Name(value='out_name'),
                        value=ast_types.StringValue(input_parameter_name)
                    )
                ]
            ),
        ]
        new_selection = ast_types.Field(
            name=ast_types.Name(value=sink_field_name),
            directives=directives
        )
        selection_set.selections.insert(0, new_selection)
