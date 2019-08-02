# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple
from copy import deepcopy

from graphql import print_ast
from graphql.language import ast as ast_types

from .utils import try_get_ast_and_index


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


# LogicalQueryPlan
StableQueryNode = namedtuple(
    'StableQueryNode', (
        'query_ast',  # Document
        'parent_stable_query_node',  # StableQueryNode
        'child_stable_query_nodes',  # List[StableQueryNode]
    )
)


OutputJoinDescriptor = namedtuple(
    'OutputJoinDescriptor', (
        'output_names',  # Tuple[str, str], should be treated as unordered
        # 'is_optional',  # boolean
        # TODO: look into fold and x_count and how to make this interact well with fold
    )
)


LogicalQueryPlanDescriptor = namedtuple(
    'LogicalQueryPlanDescriptor', (
        'root_logical_query_plan_piece',  # LogicalQueryPlanPiece
        'intermediate_output_names',  # Set[str], names of outputs to be removed
        'output_join_descriptors',  # List[OutputJoinDescriptor]
    )
)


# If @output nodes are added only when QueryNodes are turned into StableQueryNodes, then we
# can't run queries contained in QueryNodes to, say, estimate the size of outputs, because some
# such queries don't contain any outputs and are invalid.


def stabilize_and_add_directives(query_node):  # make_logical_query_plan
    """Return a StableQueryNode, with @filter and @output directives added, along with metadata.

    ASTs contained in the input will not be modified.

    Returns:
        Tuple[StableQueryNode, Set[str], List[OutputJoinDescriptor]] where the set of strings is
        the set of intermediate outputs that are to be deleted at the end.

        Make this a namedtuple?
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
            parent_output_directive, _ = try_get_ast_and_index(
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
            child_output_directive, _ = try_get_ast_and_index(
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
                _get_depth_and_asts_in_dfs_order_helper(child_stable_query_node, depth + 1)
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
                        ast_types.StringValue(value=u'$' + input_filter_name),
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
