# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple
from copy import deepcopy

from graphql import print_ast
from graphql.language import ast as ast_types

from .utils import try_get_ast


SubQueryPlan = namedtuple(
    'SubQueryPlan', (
        'query_ast',  # Document, representing a piece of the overall query with directives added
        'schema_id',  # str, identifying the schema that this query piece targets
        'parent_query_plan',  # SubQueryPlan, the query that the current query depends on
        'child_query_plans',  # List[SubQueryPlan], the queries that depend on the current query
    )
)


OutputJoinDescriptor = namedtuple(
    'OutputJoinDescriptor', (
        'output_names',  # Tuple[str, str], (parent output name, child output name)
        # 'is_optional',  # boolean, if the parent has an @optional requiring an outer join
    )
)


QueryPlanDescriptor = namedtuple(
    'QueryPlanDescriptor', (
        'root_sub_query_plan',  # SubQueryPlan
        'intermediate_output_names',  # Set[str], names of outputs to be removed at the end
        'output_join_descriptors',
        # List[OutputJoinDescriptor], describing which outputs should be joined and how
    )
)


def make_query_plan(root_sub_query_node):
    """Return a QueryPlanDescriptor, whose query ASTs have @filter and @output directives added.

    For each stitch, if the property field in the parent used in the stitch does not already
    have an @output directive, one will be added with an auto-generated out_name. The property
    field in the child will correspondingly have an @filter directive with an in_collection
    operation added. The name of the local variable in the filter directive is guaranteed to
    be identical to the outname of the parent's @output directive.

    ASTs contained in the input node and its children nodes will not be modified.

    Args:
        root_sub_query_node: SubQueryNode, representing the base of a query split into pieces
                             that we want to turn into a query plan

    Returns:
        QueryPlanDescriptor namedtuple, containing a tree of SubQueryPlans that wrap
        around each individual query AST, the set of intermediate output names that are
        to be removed at the end, and information on which outputs are to be connect to which
        in what manner
    """
    # Making the input filter name identical to the output name can cause name conflicts in a
    # very uncommon edge case, where the user has defined the parent @output, and also has
    # defined a variable with the same name.

    # The following variables are modified by the helper functions defined inside
    intermediate_output_names = set()
    output_join_descriptors = []
    _output_count = [0]  # Workaround for lack of nonlocal in python 2

    root_sub_query_plan = SubQueryPlan(
        query_ast=deepcopy(root_sub_query_node.query_ast),
        schema_id=root_sub_query_node.schema_id,
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
        output_directive = try_get_ast(field.directives, u'output', ast_types.Directive)
        if output_directive is None:
            # Create and add new directive to field
            out_name = _assign_and_return_output_name()
            output_directive = _get_output_directive(out_name)
            if field.directives is None:
                field.directives = []
            field.directives.append(output_directive)
            return out_name
        else:
            return output_directive.arguments[0].value.value  # Location of value of out_name

    def _make_query_plan_helper(sub_query_node, sub_query_plan):
        """Recursively copy the structure of sub_query_node onto sub_query_plan.

        For each child connection contained in sub_query_node, create a new SubQueryPlan for
        the corresponding child SubQueryNode, add appropriate @output and @filter directives
        to the parent and child ASTs, and attach the new SubQueryPlan to the list of children
        of the input sub query plan.

        Args:
            sub_query_node: SubQueryNode, whose descendents are copied over onto sub_query_plan.
                            It is not modified by this function
            sub_query_plan: SubQueryPlan, whose list of child query plans and query AST are
                            modified
        """
        parent_query_ast = sub_query_plan.query_ast  # Can modify and add directives directly

        # Iterate through child connections of query node
        for child_query_connection in sub_query_node.child_query_connections:
            child_sub_query_node = child_query_connection.sink_query_node
            child_query_ast = deepcopy(child_sub_query_node.query_ast)  # Prevent modifying input

            parent_field = _get_node_by_path(
                parent_query_ast, child_query_connection.source_field_path
            )
            child_field = _get_node_by_path(
                child_query_ast, child_query_connection.sink_field_path
            )

            # Get existing @output or add new to parent and child
            parent_out_name = _get_out_name_or_add_output_directive(parent_field)
            child_out_name = _get_out_name_or_add_output_directive(child_field)

            # Add @filter to child
            # Local variable in @filter will be named the same as the parent output
            child_filter_directive = _get_in_collection_filter_directive(parent_out_name)
            child_field.directives.append(child_filter_directive)

            # Create new SubQueryPlan for child
            child_sub_query_plan = SubQueryPlan(
                query_ast=child_query_ast,
                schema_id=child_sub_query_node.schema_id,
                parent_query_plan=sub_query_plan,
                child_query_plans=[],
            )

            # Add new SubQueryPlan to parent's child list
            sub_query_plan.child_query_plans.append(child_sub_query_plan)

            # Add information about this edge
            new_output_join_descriptor = OutputJoinDescriptor(
                output_names=(parent_out_name, child_out_name),
            )
            output_join_descriptors.append(new_output_join_descriptor)

            # Recursively repeat on child SubQueryPlans
            _make_query_plan_helper(child_sub_query_node, child_sub_query_plan)

    _make_query_plan_helper(root_sub_query_node, root_sub_query_plan)

    return QueryPlanDescriptor(
        root_sub_query_plan=root_sub_query_plan,
        intermediate_output_names=intermediate_output_names,
        output_join_descriptors=output_join_descriptors,
    )


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


def _get_node_by_path(ast, path):
    """Return the Node object in the input AST pointed to by the input path.

    Args:
        ast: Node
        path: List[Union[int, str]], the list of attribute names (if str) or list indices (if
              int) used to access a node in the input AST.
    """
    target_node = ast
    for key in path:
        # If both AST and path are produced normally by split_query, the below errors will only
        # occur due to programming bugs.
        if isinstance(key, str):
            try:
                target_node = getattr(target_node, key)
            except AttributeError:
                raise AssertionError(
                    u'The path {} cannot be used to index into AST {}. The attribute {} '
                    u'cannot be found in AST node {}.'.format(path, ast, key, target_node)
                )
        elif isinstance(key, int):
            if not isinstance(target_node, list):
                raise AssertionError(
                    u'The path {} cannot be used to index into AST {}. The key {} is a list '
                    u'index, but the corresponding component {} is not a list.'
                    u''.format(path, ast, key, target_node)
                )
            try:
                target_node = target_node[key]
            except IndexError:
                raise AssertionError(
                    u'The path {} cannot be used to index into AST {}. The key {} is out of '
                    u'range for {}.'.format(path, ast, key, target_node)
                )
        else:
            raise AssertionError(
                u'The path {} used for accessing a particular node in an AST should only '
                u'contain int and str elements.'.format(path)
            )
    return target_node


def print_query_plan(query_plan_descriptor):
    """Return string describing query plan."""
    query_plan_str = u''
    plan_and_depth = _get_plan_and_depth_in_dfs_order(query_plan_descriptor.root_sub_query_plan)

    for query_plan, depth in plan_and_depth:
        line_separation = u'\n' + u' ' * 8 * depth
        query_plan_str += line_separation

        query_str = u'Execute in schema named "{}":\n'.format(query_plan.schema_id)
        query_str += print_ast(query_plan.query_ast)
        query_str = query_str.replace(u'\n', line_separation)
        query_plan_str += query_str

    query_plan_str += u'\n\n'
    query_plan_str += u'Join together outputs as follows: '
    query_plan_str += str(query_plan_descriptor.output_join_descriptors) + u'\n\n'
    query_plan_str += u'Remove the following outputs at the end: '
    query_plan_str += str(query_plan_descriptor.intermediate_output_names) + u'\n'

    return query_plan_str


def _get_plan_and_depth_in_dfs_order(query_plan):
    def _get_plan_and_depth_in_dfs_order_helper(query_plan, depth):
        plan_and_depth_in_dfs_order = [(query_plan, depth)]
        for child_query_plan in query_plan.child_query_plans:
            plan_and_depth_in_dfs_order.extend(
                _get_plan_and_depth_in_dfs_order_helper(child_query_plan, depth + 1)
            )
        return plan_and_depth_in_dfs_order
    return _get_plan_and_depth_in_dfs_order_helper(query_plan, 0)


# Ok, conclusion:
# Keep track of set of user output columns, update parent set with union when joining
# Can also keep track of set of intermediate columns that we assigned
# Delete all non-user-output columns at the very end
# Columns have globally unique names
# Each merging edge keeps track of names of parent and child columns, as well as any additional
#   information (is optional join, etc)
# When merging, both columns are kept
# Fail if merging with both ends being user output?
