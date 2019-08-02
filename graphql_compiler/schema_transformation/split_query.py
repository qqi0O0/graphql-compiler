from collections import namedtuple
from copy import copy, deepcopy

from graphql import build_ast_schema, print_ast
from graphql.language import ast as ast_types
from graphql.language.visitor import TypeInfoVisitor, Visitor, visit
from graphql.type.definition import GraphQLList, GraphQLNonNull, GraphQLUnionType
from graphql.utils.type_info import TypeInfo


# Break down into two steps, one for splitting the tree with minimum modifications (just adding
# the type on the outermost scope) and keeping track of connecting edge information, one for
# modifying the split tree with appropriate @filter and @output directives
# The second step will also need to keep track of what actual user outputs are


QueryConnection = namedtuple(
    'QueryConnection', (
        'sink_query_node',  # QueryNode
        'source_field_path',  # List[Union[int, str]]
        'sink_field_path',  # List[Union[int, str]]
    )
)
# NOTE: using these paths does mean that we can't insert or delete nodes, only append or replace
# by None


def get_node_by_path(ast, path):
    target_node = ast
    for key in path:
        if isinstance(key, str):
            target_node = getattr(target_node, key)
        elif isinstance(key, int):
            target_node = target_node[key]
        else:
            raise AssertionError(u'')
    return target_node


class QueryNode(object):
    def __init__(self, query_ast):  # schema_id?
        self.query_ast = query_ast
        self.parent_query_connection = None
        self.child_query_connections = []
        # probably ok to just have input_filter_name be equal to the parent's output column
        # name
        # This will cause issues in a rare edge case, where the parent's output is user defined,
        # and this out_name conflicts with the name of another local variable.

    def reroot_tree(self):
        pass


def split_query(query_ast, merged_schema_descriptor):
    """Split input query AST into a tree of QueryNodes targeting each individual schema.

    Additional @output and @filter directives will not be added in this step. Fields that make
    up the stitch will be added if necessary. The connection between QueryNodes will contain
    those fields used in stitching, so that they can easily be modified to include more
    directives.

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
    query_ast = deepcopy(query_ast)
    # If schema directives are correctly represented in the schema object, type_info is all
    # that's needed to detect and address stitching fields. However, before this issue is
    # fixed, it's necessary to use additional information from preprocessing the schema AST
    edge_to_stitch_fields = _get_edge_to_stitch_fields(merged_schema_descriptor)

    base_query_node = QueryNode(query_ast)
    type_info = TypeInfo(build_ast_schema(merged_schema_descriptor.schema_ast))
    query_nodes_to_visit = [base_query_node]

    # Construct full tree of QueryNodes in a dfs pattern
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
    # TODO: record down schema id and check schema id when entering Field or InlineFragment
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

    # TODO: currently there is no validation nor schema_id in base_query_node, but should
    # check that every type visited lies inside the correct schema
    # Check type_info.get_type not get_parent_type, because parent of the base type is
    # RootSchemaQuery

    def enter_Field(self, node, key, parent, path, *args):
        """Check for split at the current field.

        If there is a new split at this field as clued by a @stitch directive, a new Document
        will be created containing the current branch, with a new field 

        If there is a new split as clued by a @stitch directive, a new Document will be created
        containing the current branch, with some modifications at the root. The new Document
        will be wrapped in a QueryNode, and added to query_nodes_stack. The rest of the branch
        will not be visited.

        Args:
            node: Node
            key: str
            parent: List[Union[Field, InlineFragment]], containing all other fields or typ
                    coercions in this selection
            path: List[Union[int, str]], listing the attribute names or list indices used to
                  index into the AST, starting from the root, to reach the current node
        """
        if self._try_get_stitch_fields(node) is None:
            return
        parent_field_name, child_field_name = self._try_get_stitch_fields(node)

        # Get root vertex field name and selection set of the cut off branch of the AST
        child_type_name, child_selection_set = \
            self._get_child_root_vertex_field_name_and_selection_set(node)

        # Check for existing field in parent
        parent_field, parent_field_index = _try_get_ast_and_index(
            parent, parent_field_name, ast_types.Field
        )
        # Process parent field, and get parent field path
        if parent_field is None:
            # Change stump field to source field
            # TODO: process existing directives
            node.name.value = parent_field_name
            node.selection_set = []
            parent_field_path = copy(path)
        else:
            # Remove stump field
            # Can't delete field, since that interferes with both the visitor's traversal and the
            # field paths in QueryConnections, and thus replace by None
            parent[key] = None
            parent_field_path = copy(path)
            parent_field_path[-1] = parent_field_index  # Change last (current node) index

        # Check for existing field in child
        child_field, child_field_index = _try_get_ast_and_index(
            child_selection_set.selections, child_field_name, ast_types.Field
        )
        # Process child field, and get child field path
        if child_field is None:
            # Add new field to end of child's selection set
            child_field = ast_types.Field(
                name=ast_types.Name(value=child_field_name),
                directives=[],
            )
            child_selection_set.selections.append(child_field)
            child_field_path = [
                'definitions', 0, 'selection_set', 'selections', 0, 'selection_set', 'selections',
                len(child_selection_set.selections)-1
            ]
        else:
            child_field_path = [
                'definitions', 0, 'selection_set', 'selections', 0, 'selection_set', 'selections',
                child_field_index
            ]
        # Create child AST for the pruned branch, and child QueryNode for the AST
        child_query_ast = self._create_query_document(child_type_name, child_selection_set)
        child_query_node = QueryNode(child_query_ast)

        # Create and add QueryConnection to parent and child
        self._add_query_connections(self.base_query_node, child_query_node, parent_field_path,
                                    child_field_path)
        # TODO: deal with None as opposed to empty lists in various places

        # Returning False causes visit to skip visiting the rest of the branch
        return False

    def _try_get_stitch_fields(self, node):
        """Return names of parent and child stitch fields, or None if there is no stitch."""
        # Get whether or not there is a stitch here, based on name of the type and field
        # This is only necessary because schemas do not keep track of schema directives
        # correctly. Once that is fixed, TypeInfo should be all that's needed to check for
        # stitch directives, and edge_to_stitch_fields can be removed.
        parent_type_name = self.type_info.get_parent_type().name
        edge_field_name = node.name.value
        edge_field_descriptor = (parent_type_name, edge_field_name)

        if not edge_field_descriptor in self.edge_to_stitch_fields:  # no stitch at this field
            return None

        return self.edge_to_stitch_fields[edge_field_descriptor]

    def _get_child_root_vertex_field_name_and_selection_set(self, node):
        """Get the root field name and selection set of the child AST split at the input node.

        Takes care of type coercion, so the root field name will be the coerced type rather than
        a, say, union type, and the selection set will contain real fields rather than a single
        inline fragment.

        node must be the node that the visitor is currently on, to ensure that self.type_info
        matches up with node.

        Args:
            node: Node

        Returns:
            Tuple[str, SelectionSet], name and selection set of the child branch of the AST
            cut off at node.
        """
        child_type = self.type_info.get_type()  # GraphQLType, may be wrapped in List or NonNull
        # assert that sink_type is a GraphQLList?
        # NOTE: how does NonNull for sink_type affect anything?
        while isinstance(child_type, (GraphQLList, GraphQLNonNull)):
            child_type = child_type.of_type
        child_type_name = child_type.name
        child_selection_set = node.selection_set

        # Adjust for type coercion due to the sink_type being an interface or union
        if (
            len(child_selection_set.selections) == 1 and
            isinstance(child_selection_set.selections[0], ast_types.InlineFragment)
        ):
            type_coercion_inline_fragment = child_selection_set.selections[0]
            child_type_name = type_coercion_inline_fragment.type_condition.name.value
            child_selection_set = type_coercion_inline_fragment.selection_set

        return (child_type_name, child_selection_set)

    def _create_query_document(self, root_vertex_field_name, root_selection_set):
        """Return a Document representing a query with the specified name and selection set."""
        return ast_types.Document(
            definitions=[
                ast_types.OperationDefinition(
                    operation='query',
                    selection_set=ast_types.SelectionSet(
                        selections=[
                            ast_types.Field(
                                name=ast_types.Name(value=root_vertex_field_name),
                                selection_set=root_selection_set,
                                directives=[],
                            )
                        ]
                    )
                )
            ]
        )

    def _add_query_connections(self, parent_query_node, child_query_node, parent_field_path,
                               child_field_path):
        """Modify parent and child QueryNodes by adding appropriate QueryConnections."""
        # Create QueryConnections
        new_query_connection_from_parent = QueryConnection(
            sink_query_node=child_query_node,
            source_field_path=parent_field_path,
            sink_field_path=child_field_path,
        )
        new_query_connection_from_child = QueryConnection(
            sink_query_node=self.base_query_node,
            source_field_path=child_field_path,
            sink_field_path=parent_field_path,
        )
        # Add QueryConnections
        parent_query_node.child_query_connections.append(new_query_connection_from_parent)
        child_query_node.parent_query_connection = new_query_connection_from_child


# Does this really need to be so structured? We can just have a list of pairs of strings, each
# pair describing the names of two columns that need to be stitched
StableQueryNode = namedtuple(
    'StableQueryNodes', (
        'query_ast',  # Document
        'parent_stable_query_node',  # StableQueryNode
        'child_stable_query_nodes',  # List[StableQueryNode]
    )
)


OutputJoinDescriptor = namedtuple(
    'OutputJoinDescriptor', (
        'output_names',  # Tuple[str, str], should be treated as unordered
#        'is_optional',  # boolean
    )
)


# in which step is the output directive added? If add in step 2, then can't run nodes of step
# 1 because some queries lack @output and are invalid
# worry about this later


def stabilize_and_add_directives(query_node):
    """Return a StableQueryNode, with @filter and @output directives added, along with metadata.

    ASTs contained in the input will not be modified.

    Returns:
        Tuple[StableQueryNode, Set[str], List[OutputJoinDescriptor]] where the set of strings is
        the set of intermediate outputs that are to be deleted at the end. Make this a
        namedtuple?
    """
    intermediate_output_names = set()
    output_join_descriptors = []
    _output_count = [0]

    base_stable_query_node = StableQueryNode(
        query_ast=deepcopy(query_node.query_ast),
        parent_stable_query_node=None,
        child_stable_query_nodes=[],
    )

    def _assign_and_return_output_name():
        output_name = u'__intermediate_output_' + str(_output_count[0])
        _output_count[0] += 1
        return output_name

    def _stabilize_and_add_directives_helper(query_node, stable_query_node):
        """Recursively build the structure of query_node onto stable_query_node.

        stable_query_node is assumed to have its parent connections processed. This function
        will process its child connections and create new StableQueryNodes recursively as
        needed.

        Modifies the list of children of stable_query_node.
        """
        parent_query_ast = stable_query_node.query_ast

        # Iterate through child connections of query node
        for child_query_connection in query_node.child_query_connections:
            child_query_node = child_query_connection.sink_query_node
            child_query_ast = deepcopy(child_query_node.query_ast)

            parent_field = get_node_by_path(
                parent_query_ast, child_query_connection.source_field_path
            )
            child_field = get_node_by_path(
                child_query_ast, child_query_connection.sink_field_path
            )

            # Get existing @output or add @output to parent
            parent_output_directive, _ = _try_get_ast_and_index(
                parent_field.directives, u'output', ast_types.Directive
            )
            if parent_output_directive is None:
                # Create and add new directive to field, add to intermediate_output_names
                parent_out_name = _assign_and_return_output_name()
                intermediate_output_names.add(parent_out_name)
                parent_output_directive = _get_output_directive(parent_out_name)
                parent_field.directives.append(parent_output_directive)
            else:
                parent_out_name = parent_output_directive.arguments[0].value.value

            # Get existing @output or add @output to child
            child_output_directive, _ = _try_get_ast_and_index(
                child_field.directives, u'output', ast_types.Directive
            )
            if child_output_directive is None:
                # Create and add new directive to field, add to intermediate_output_names
                child_out_name = _assign_and_return_output_name()
                intermediate_output_names.add(child_out_name)
                child_output_directive = _get_output_directive(child_out_name)
                child_field.directives.append(child_output_directive)
            else:
                child_out_name = child_output_directive.arguments[0].value.value

            # Add @filter to child
            # Local variable in @filter will be named the same as the parent output
            # Only add, don't change existing filters?
            child_filter_directive = _get_in_collection_filter_directive(parent_out_name)
            child_field.directives.append(child_filter_directive)

            # Create new StableQueryNode for child
            child_stable_query_node = StableQueryNode(
                query_ast=child_query_ast,
                parent_stable_query_node=query_node,
                child_stable_query_nodes=[],
            )

            # Add new StableQueryNode to parent's child list
            stable_query_node.child_stable_query_nodes.append(child_stable_query_node)

            # Add information about this edge
            new_output_join_descriptor = OutputJoinDescriptor(
                output_names=(parent_out_name, child_out_name),
            )
            output_join_descriptors.append(new_output_join_descriptor)

            # Recursively repeat on child StableQueryNode
            _stabilize_and_add_directives_helper(child_query_node, child_stable_query_node)

    _stabilize_and_add_directives_helper(query_node, base_stable_query_node)
    return (base_stable_query_node, intermediate_output_names, output_join_descriptors)


def _get_depth_and_asts_in_dfs_order(stable_query_node):
    def _get_depth_and_asts_in_dfs_order_helper(stable_query_node, depth):
        asts_in_dfs_order = [(depth, stable_query_node.query_ast)]
        for child_stable_query_node in stable_query_node.child_stable_query_nodes:
            asts_in_dfs_order.extend(
                _get_depth_and_asts_in_dfs_order_helper(child_stable_query_node, depth+1)
            )
        return asts_in_dfs_order
    return _get_depth_and_asts_in_dfs_order_helper(stable_query_node, 0)


def print_query_plan(stable_query_node):
    """Return string describing query plan."""

    query_plan = u''
    depths_and_asts = _get_depth_and_asts_in_dfs_order(stable_query_node)

    for depth, query_ast in depths_and_asts:
        line_separation = u'\n' + u' ' * 8 * depth
        query_plan += line_separation

        query_str = print_ast(query_ast)
        query_str = query_str.replace(u'\n', line_separation)
        query_plan += query_str

    return query_plan




    # @output directives can be attached before order of the tree is known, but @filter and
    # information on what column is put into what filter must come after the order of the tree
    # is known


def _get_edge_to_stitch_fields(merged_schema_descriptor):
    """Get a map from type/field of each cross schema edge, to the fields that the edge stitches.

    This is necessary only because graphql currently doesn't process schema directives correctly.
    Once schema directives are correctly added to GraphQLSchema objects, this part may be
    removed as directives on a schema field can be directly accessed.

    Args:
        merged_schema_descriptor: MergedSchemaDescriptor namedtuple, containing a schema ast
                                  and a map from names of types to their schema ids

    Returns:
        Dict[Tuple(str, str), Tuple(str, str)], mapping (type name, edge field name) to
        (source field name, sink field name) used in the @stitch directive, for each cross
        schema edge
    """
    edge_to_stitch_fields = {}
    for type_definition in merged_schema_descriptor.schema_ast.definitions:
        if isinstance(type_definition, (
            ast_types.ObjectTypeDefinition, ast_types.InterfaceTypeDefinition
        )):
            for field_definition in type_definition.fields:
                stitch_directive, _ = _try_get_ast_and_index(
                    field_definition.directives, u'stitch', ast_types.Directive
                )
                if stitch_directive is not None:
                    source_field_name = stitch_directive.arguments[0].value.value
                    sink_field_name = stitch_directive.arguments[1].value.value
                    edge = (type_definition.name.value, field_definition.name.value)
                    edge_to_stitch_fields[edge] = (source_field_name, sink_field_name)

    return edge_to_stitch_fields


def _try_get_ast_and_index(asts, target_name, target_type):
    """Return the ast and its index in the list with the desired name and type, if found.

    Args:
        asts: List[Node] or None
        target_name: str, name of the AST we're looking for
        target_type: Node, the type of the AST we're looking for. Must be a type with a .name
                     attribute, e.g. Field, Directive

    Returns:
        Tuple[Node, int], an element in the input list of ASTs of the correct name and type, and
        the index of this element in the list, if found. If not found, return (None, None)
    """
    if asts is None:
        return (None, None)
    # Check there is only one?
    for index, ast in enumerate(asts):
        if isinstance(ast, target_type):
            if ast.name.value == target_name:
                return (ast, index)
    return (None, None)


def _get_output_directive(out_name):
    return ast_types.Directive(
        name=ast_types.Name(value=u'output'),
        arguments=[
            ast_types.Argument(
                name=ast_types.Name(value=u'out_name'),
                value=ast_types.StringValue(value=out_name),
            ),
        ],
    )

def _get_in_collection_filter_directive(input_filter_name):
    return ast_types.Directive(
        name=ast_types.Name(value=u'filter'),
        arguments=[
            ast_types.Argument(
                name=ast_types.Name(value='op_name'),
                value=ast_types.StringValue(value='in_collection'),
            ),
            ast_types.Argument(
                name=ast_types.Name(value='value'),
                value=ast_types.ListValue(
                    values=[
                        ast_types.StringValue(value=u'$'+input_filter_name),
                    ],
                ),
            ),
        ],
    )


# Ok, conclusion:
# Keep track of set of user output columns, update parent set with union when joining
# Can also keep track of set of intermediate columns that we assigned
# Delete all non-user-output columns at the very end
# Columns have globally unique names
# Each merging edge keeps track of names of parent and child columns, as well as any additional
#   information (is optional join, etc)
# When merging, both columns are kept
# Fail if merging with both ends being user output?
