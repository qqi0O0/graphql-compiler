# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple
from copy import copy, deepcopy

from graphql import build_ast_schema
from graphql.language import ast as ast_types
from graphql.language.visitor import TypeInfoVisitor, Visitor, visit
from graphql.type.definition import GraphQLList, GraphQLNonNull
from graphql.utils.type_info import TypeInfo

from ..exceptions import GraphQLValidationError
from .utils import try_get_ast_and_index


QueryConnection = namedtuple(
    'QueryConnection', (
        'sink_query_node',  # QueryNode
        'source_field_path',  # List[Union[int, str]]
        'sink_field_path',  # List[Union[int, str]]
    )
)


class QueryNode(object):
    def __init__(self, query_ast):  # schema_id?
        """Represents one piece of a larger query, targeting one schema.

        Args:
            query_ast: Document, representing one piece of a query
        """
        self.query_ast = query_ast
        self.schema_id = None  # str, identifying the schema that this query targets
        self.parent_query_connection = None
        # QueryNode or None, the query that the current query depends on
        self.child_query_connections = []
        # List[QueryNode], the queries that depend on the current query


def split_query(query_ast, merged_schema_descriptor):
    """Split input query AST into a tree of QueryNodes targeting each individual schema.

    Additional @output and @filter directives will not be added in this step. Fields that make
    up the stitch will be added if necessary. The connection between QueryNodes will contain
    the path to get those fields used in stitching, so that they can be modified to include
    more directives.

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
    # Only supported directives are @optional, @output, and @filter
    query_ast = deepcopy(query_ast)
    # If schema directives are correctly represented in the schema object, type_info is all
    # that's needed to detect and address stitching fields. However, before this issue is
    # fixed, it's necessary to use additional information from preprocessing the schema AST
    edge_to_stitch_fields = _get_edge_to_stitch_fields(merged_schema_descriptor)

    root_query_node = QueryNode(query_ast)
    type_info = TypeInfo(merged_schema_descriptor.schema)
    query_nodes_to_visit = [root_query_node]

    # Construct full tree of QueryNodes in a dfs pattern
    while len(query_nodes_to_visit) > 0:
        current_node_to_visit = query_nodes_to_visit.pop()
        # visit will break down the ast included inside current_node_to_visit into potentially
        # multiple query nodes, all added to child_query_nodes list of current_node_to_visit
        split_query_visitor = SplitQueryVisitor(
            type_info, edge_to_stitch_fields, merged_schema_descriptor.type_name_to_schema_id,
            current_node_to_visit
        )
        visitor = TypeInfoVisitor(type_info, split_query_visitor)
        visit(current_node_to_visit.query_ast, visitor)
        query_nodes_to_visit.extend(
            child_query_connection.sink_query_node
            for child_query_connection in current_node_to_visit.child_query_connections
        )

    return root_query_node


class SplitQueryVisitor(Visitor):
    """Prune branches of AST and build tree of QueryNodes while visiting."""
    def __init__(self, type_info, edge_to_stitch_fields, type_name_to_schema_id, root_query_node):
        """Create a QueryNode with one level of children from the visited AST.

        The visitor will modify the AST by cutting off branches where stitches occur, and
        modify the root_query_node by creating a QueryNode for every cut-off branch and
        connecting these new QueryNodes to the root_query_node.

        Args:
            type_info: TypeInfo
            edge_to_stitch_fields: Dict[Tuple[str, str], Tuple[str, str]], mapping
                                   (name of type, name of field representing the edge) to
                                   (source field name, sink field name)
            type_name_to_schema_id: Dict[str, str], mapping name of each type to the id of the
                                    schema it came from
            root_query_node: QueryNode, its query_ast and child_query_connections are modified
        """
        self.type_info = type_info
        self.edge_to_stitch_fields = edge_to_stitch_fields
        self.type_name_to_schema_id = type_name_to_schema_id
        self.root_query_node = root_query_node

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
            parent: List[Union[Field, InlineFragment]], containing all other fields or type
                    coercions in this selection
            path: List[Union[int, str]], listing the attribute names or list indices used to
                  index into the AST, starting from the root, to reach the current node
        """
        # Get root vertex field name and selection set of current branch of the AST
        child_type_name, child_selection_set = \
            self._get_child_root_vertex_field_name_and_selection_set(node)

        if self._try_get_stitch_fields(node) is None:
            # Check or set the schema id of the end of the edge that does not cross the schema
            self._check_or_set_schema_id(child_type_name)
            return
        parent_field_name, child_field_name = self._try_get_stitch_fields(node)

        # Check for existing field in parent
        parent_field, parent_field_index = try_get_ast_and_index(
            parent, parent_field_name, ast_types.Field
        )
        # Process parent field, and get parent field path
        if parent_field is None:
            # Change stump field to source field
            # TODO: process existing directives, especially @optional and @fold
            # currently directives are just passed down
            node.name.value = parent_field_name
            node.selection_set = []
            parent_field_path = copy(path)
        else:
            # Remove stump field
            # Can't delete field, since that interferes with both the visitor's traversal and the
            # field paths in QueryConnections, and thus replace by None
            # TODO: add any existing directives on parent field onto the field we found
            parent[key] = None
            parent_field_path = copy(path)
            parent_field_path[-1] = parent_field_index  # Change last (current node) index

        # Check for existing field in child
        child_field, child_field_index = try_get_ast_and_index(
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
                len(child_selection_set.selections) - 1
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
        self._add_query_connections(self.root_query_node, child_query_node, parent_field_path,
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

        if edge_field_descriptor not in self.edge_to_stitch_fields:  # no stitch at this field
            return None

        return self.edge_to_stitch_fields[edge_field_descriptor]

    def _check_or_set_schema_id(self, type_name):
        """Set the schema id of the root node if not yet set, otherwise check schema ids agree.

        Args:
            type_name: str, name of the type those schema id we're comparing against the
                       current schema id, if any
        """
        # TODO: use on InlineFragment?
        # If want to have the below error message, need to keep track of scalars as well
        # if type_name not in self.type_name_to_schema_id:
        #     raise GraphQLValidationError(
        #         u'Type "{}" is not found in the record of types.'.format(type_name)
        #     )
        if type_name in self.type_name_to_schema_id:
            current_type_schema_id = self.type_name_to_schema_id[type_name]
            prior_type_schema_id = self.root_query_node.schema_id
            if prior_type_schema_id is None:  # First time checking schema_id
                self.root_query_node.schema_id = current_type_schema_id
            elif current_type_schema_id != prior_type_schema_id:
                # merged_schema_descriptor invalid, an edge field without a @stitch directive
                # crosses schemas
                raise AssertionError(u'')

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
            Tuple[str, SelectionSet or None], name and selection set of the child branch of
            the AST cut off at node. If the node is a property field, it will have no selection
            set
        """
        # TODO: can get bad error messages due to TypeInfo dying from bad queries
        child_type = self.type_info.get_type()  # GraphQLType, may be wrapped in List or NonNull
        # assert that sink_type is a GraphQLList?
        # NOTE: how does NonNull for sink_type affect anything?
        while isinstance(child_type, (GraphQLList, GraphQLNonNull)):
            child_type = child_type.of_type
        child_type_name = child_type.name
        child_selection_set = node.selection_set

        # Adjust for type coercion due to the sink_type being an interface or union
        if (
            child_selection_set is not None and  # Not a property field
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
            sink_query_node=self.root_query_node,
            source_field_path=child_field_path,
            sink_field_path=parent_field_path,
        )
        # Add QueryConnections
        parent_query_node.child_query_connections.append(new_query_connection_from_parent)
        child_query_node.parent_query_connection = new_query_connection_from_child

    def leave_Document(self, node, *args):
        # Confirm that schema_id has been filled in
        if self.root_query_node.schema_id is None:
            raise AssertionError(u'')


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
                stitch_directive, _ = try_get_ast_and_index(
                    field_definition.directives, u'stitch', ast_types.Directive
                )
                if stitch_directive is not None:
                    source_field_name = stitch_directive.arguments[0].value.value
                    sink_field_name = stitch_directive.arguments[1].value.value
                    edge = (type_definition.name.value, field_definition.name.value)
                    edge_to_stitch_fields[edge] = (source_field_name, sink_field_name)

    return edge_to_stitch_fields
