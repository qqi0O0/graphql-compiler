# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple
from copy import deepcopy

from graphql import print_ast
from graphql.language import ast as ast_types
from graphql.language.visit import visit, Visitor

from ..exceptions import GraphQLValidationError
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
        # 'is_optional',
        # May be expanded to have more attributes, describing how the join should be made
    )
)


QueryPlanDescriptor = namedtuple(
    'QueryPlanDescriptor', (
        'root_sub_query_plan',  # SubQueryPlan
        'intermediate_output_names',  # frozenset[str], names of outputs to be removed at the end
        'output_join_descriptors',
        # List[OutputJoinDescriptor], describing which outputs should be joined and how
    )
)


# NOTE: now this part only adds @filter directives, @output have been added
# Change doc strings


def make_query_plan(root_sub_query_node, intermediate_output_names):
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
    output_join_descriptors = []

    root_sub_query_plan = SubQueryPlan(
        query_ast=root_sub_query_node.query_ast,  # NOTE: careful about no modifications
        schema_id=root_sub_query_node.schema_id,
        parent_query_plan=None,
        child_query_plans=[],
    )

    _make_query_plan_recursive(root_sub_query_node, root_sub_query_plan)

    return QueryPlanDescriptor(
        root_sub_query_plan=root_sub_query_plan,
        intermediate_output_names=intermediate_output_names,
        output_join_descriptors=output_join_descriptors,
    )


def _make_query_plan_recursive(sub_query_node, sub_query_plan):
    """Recursively copy the structure of sub_query_node onto sub_query_plan.

    For each child connection contained in sub_query_node, create a new SubQueryPlan for
    the corresponding child SubQueryNode, add appropriate @filter directive to the child AST,
    and attach the new SubQueryPlan to the list of children of the input sub query plan.

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
        parent_out_name = child_query_connection.source_field_out_name
        child_out_name = child_query_connection.sink_field_out_name

        child_query_ast = child_sub_query_node.query_ast
        child_query_ast_with_filter = _add_filter_at_field_with_output(
            child_query_ast, child_out_name, parent_out_name
            # @filter's local variable is named the same as the out_name of the parent's @output
        )
        if child_query_ast is child_query_ast_with_filter:
            raise AssertionError(
                u'An @output directive with out_name "{}" is unexpectedly not found in the '
                u'AST "{}".'.format(child_out_name, child_query_ast)
            )

        # Create new SubQueryPlan for child
        child_sub_query_plan = SubQueryPlan(
            query_ast=child_query_ast_with_filter,
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


def _add_filter_at_field_with_output(ast, field_out_name, input_filter_name):
    """Return an AST with @filter added at the field with the specified @output, if found.

    Input ast not modified.

    If not edited, return the exact input ast object.
    """
    if not isinstance(ast, (
        ast_types.Field, ast_types.InlineFragment, ast_types.OperationDefinition
    )):
        return ast

    if isinstance(ast, ast_types.Field):
        # Check whether this field has the expected directive, if so, modify and return
        if (
            ast.directives is not None and
            any(
                _is_output_directive_with_name(directive, field_out_name)
                for directive in ast.directives
            )
        ):
            new_directives = copy(ast.directives)
            new_directives.append(_get_in_collection_filter_directive(input_filter_name))
            new_ast = copy(ast)
            new_ast.directives = new_directives
            return new_ast

    if ast.selection_set is None:  # Nothing to recurse on
        return ast

    # Otherwise, recurse and look for field with name
    made_changes = False
    new_selections = []
    for selection in ast.selection_set.selections:
        new_selection = _add_filter_at_field_with_output(
            selection, field_out_name, input_filter_name
        )
        if new_selection is not selection:  # Changes made somewhere down the line
            if not made_changes:
                made_changes = True
            else:
                # Change has already been made, but there is a new change. Implies that multiple
                # fields have the @output directive with the desired name
                raise GraphQLValidationError(
                    u'There are multiple @output directives with the out_name "{}"'.format(
                        field_out_name
                    )
                )
        new_selections.append(new_selection)

    if made_changes:
        new_ast = copy(ast)
        new_ast.selection_set = ast_types.SelectionSet(selections=new_selections)
        return new_ast
    else:
        return ast


def _is_output_directive_with_name(directive, out_name):
    if not isinstance(directive, ast_types.Directive):
        raise AssertionError(u'Input "{}" is not a directive.'.format(directive))
    return directive.name.value == u'output' and directive.arguments[0].value.value == out_name


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
