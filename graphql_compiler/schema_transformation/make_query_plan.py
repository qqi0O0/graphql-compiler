# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple
from copy import deepcopy

from graphql import print_ast
from graphql.language import ast as ast_types

from .utils import try_get_ast_and_index


SubQueryPlan = namedtuple(
    'SubQueryPlan', (
        'query_ast',  # Document
        'parent_query_plan',  # SubQueryPlan
        'child_query_plans',  # List[SubQueryPlan]
    )
)


OutputJoinDescriptor = namedtuple(
    'OutputJoinDescriptor', (
        'output_names',  # Tuple[str, str], should be treated as unordered
        # 'is_optional',  # boolean
        # TODO: look into fold and x_count and how to make this interact well with fold
    )
)


QueryPlanDescriptor = namedtuple(
    'QueryPlanDescriptor', (
        'root_sub_query_plan',  # SubQueryPlan
        'intermediate_output_names',  # Set[str], names of outputs to be removed
        'output_join_descriptors',  # List[OutputJoinDescriptor]
    )
)


# If @output nodes are added only when QueryNodes are turned into StableQueryNodes, then we
# can't run queries contained in QueryNodes to, say, estimate the size of outputs, because some
# such queries don't contain any outputs and are invalid.



def make_query_plan(root_sub_query_node):
    """Return a QueryPlanDescriptor, whose query pieces have @filter and @output directives added.

    ASTs contained in the input node and its children nodes will not be modified.

    The name of the variable used in each @filter directive is identical to the outname of the
    parent's @output directive.

    Args:
        root_sub_query_node: SubQueryNode, representing the base of a query split into pieces
                             that we want to turn into a query plan

    Returns:
        QueryPlanDescriptor namedtuple, containing a tree of individual SubQueryPlans that
        wrap around each individual query AST, the set of intermediate output names that are
        to be removed at the end, and information on which outputs are to be connect to which
    """
    # Making the input filter name identical to the output name can cause name conflicts in a
    # very uncommon edge case, where the user has defined the parent @output, and also has
    # defined a variable with the same name.

    # The following variables are modified by the helper functions defined inside
    intermediate_output_names = set()
    output_join_descriptors = []
    _output_count = [0]  # Workaround for lack of nonlocal in python 2

    root_sub_query_plan = SubQueryPlan(
        query_ast=deepcopy(query_node.query_ast),
        parent_query_plan=None,
        child_query_plans=[],
    )

    def _assign_and_return_output_name():
        """Create intermediate name, increment count, add to record of intermediate outputs."""
        output_name = u'__intermediate_output_' + str(_output_count[0])
        _output_count[0] += 1
        intermediate_output_names.add(output_name)
        return output_name

    def _get_out_name_or_add_output_directive(field):
        """Return out_name of @output on field, creating new @output if needed.

        Args:
            field: Field object, whose directives we may modify
        """
        # Check for existing directive
        output_directive, _ = try_get_ast_and_index(
            field.directives, u'output', ast_types.Directive
        )
        if output_directive is None:
            # Create and add new directive to field
            out_name = _assign_and_return_output_name()
            output_directive = _get_output_directive(out_name)
            field.directives.append(output_directive)
            return out_name
        else:
            return output_directive.arguments[0].value.value  # Location of value of out_name

    def _make_query_plan_helper(sub_query_node, sub_query_plan):
        """Recursively copy the structure of sub_query_node onto sub_query_plan.

        For each child connection contained in sub_query_node, create a new SubQueryPlan for
        the corresponding child SubQueryNode, add appropriate @output and @filter directives
        to the parent and child ASTs, and attach the new SubQueryPlan to the input
        sub_query_plan.

        Args:
            sub_query_node: SubQueryNode, whose children are copied over; not modified by this
                            function
            sub_query_plan: SubQueryPlan, whose list of child query plans and query AST are
                            modified
        """
        parent_query_ast = sub_query_plan.query_ast  # Can modify and add directives

        # Iterate through child connections of query node
        for child_query_connection in query_node.child_query_connections:
            child_sub_query_node = child_query_connection.sink_query_node
            child_query_ast = deepcopy(child_sub_query_node.query_ast)  # Prevent modifying input

            parent_field = get_node_by_path(
                parent_query_ast, child_query_connection.source_field_path
            )
            child_field = get_node_by_path(
                child_query_ast, child_query_connection.sink_field_path
            )

            # Get existing @output or add new to parent and child
            parent_out_name = _get_out_name_or_add_output_directive(parent_field)
            child_out_name = _get_out_name_or_add_output_directive(child_field)

            # Add @filter to child
            # Local variable in @filter will be named the same as the parent output
            # Only add, don't change existing filters?
            child_filter_directive = _get_in_collection_filter_directive(parent_out_name)
            child_field.directives.append(child_filter_directive)

            # Create new SubQueryPlan for child
            child_sub_query_plan = SubQueryPlan(
                query_ast=child_query_ast,
                parent_query_plan=sub_query_plan,
                child_query_plans=[],
            )

            # Add new StableQueryNode to parent's child list
            sub_query_plan.child_query_plans.append(child_sub_query_plan)

            # Add information about this edge
            new_output_join_descriptor = OutputJoinDescriptor(
                output_names=(parent_out_name, child_out_name),
            )
            output_join_descriptors.append(new_output_join_descriptor)

            # Recursively repeat on child StableQueryNode
            _make_query_plan_helper(child_sub_query_node, child_sub_query_plan)

    _make_query_plan_helper(root_sub_query_node, root_sub_query_plan)

    return QueryPlanDescriptor(
        root_sub_query_plan=root_sub_query_plan,
        intermediate_output_names=intermediate_output_names,
        output_join_descriptors=output_join_descriptors,
    )


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


def _get_depth_and_asts_in_dfs_order(query_plan):
    def _get_depth_and_asts_in_dfs_order_helper(query_plan, depth):
        asts_in_dfs_order = [(depth, query_plan.query_ast)]
        for child_query_plan in query_plan.child_stable_query_nodes:
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