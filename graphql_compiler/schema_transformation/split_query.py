# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple
from copy import copy, deepcopy

from graphql import print_ast
from graphql.language import ast as ast_types
from graphql.language.visitor import TypeInfoVisitor, Visitor, visit, REMOVE
from graphql.type.definition import GraphQLList, GraphQLNonNull
from graphql.utils.type_info import TypeInfo
from graphql.validation import validate

from ..ast_manipulation import get_only_query_definition
from ..exceptions import GraphQLValidationError
from .utils import SchemaStructureError, try_get_ast


QueryConnection = namedtuple(
    'QueryConnection', (
        'sink_query_node',  # SubQueryNode
        'source_field_output_name',
        # str, the unique out name on the @output of the the source property field in the stitch
        'sink_field_output_name',
        # str, the unique out name on the @output of the the sink property field in the stitch
    )
)


class SubQueryNode(object):
    def __init__(self, query_ast):
        """Represents one piece of a larger query, targeting one schema.

        Args:
            query_ast: Document, representing one piece of a query
        """
        self.query_ast = query_ast
        self.schema_id = None  # str, identifying the schema that this query targets
        self.parent_query_connection = None
        # SubQueryNode or None, the query that the current query depends on
        self.child_query_connections = []
        # List[SubQueryNode], the queries that depend on the current query


class IntermediateOutNameAssigner(object):
    def __init__(self):
        self.intermediate_output_names = set()
        self.intermediate_output_count = 0

    def assign_and_return_out_name(self):
        out_name = '__intermediate_output_' + str(self.intermediate_output_count)
        self.intermediate_output_count += 1
        self.intermediate_output_names.add(out_name)
        return out_name


def split_query(query_ast, merged_schema_descriptor):
    """Split input query AST into a tree of SubQueryNodes targeting each individual schema.

    Additional @output and @filter directives will not be added in this step. Property fields
    used in the stitch will be added if not already present. The connection between
    SubQueryNodes will contain the paths used to reach these property fields, so that they can
    be modified to include more directives.

    Args:
        query_ast: Document, representing a GraphQL query to split
        merged_schema_descriptor: MergedSchemaDescriptor namedtuple, containing:
                                  schema_ast: Document representing the merged schema
                                  schema: GraphQLSchema representing the merged schema
                                  type_name_to_schema_id: Dict[str, str], mapping name of each
                                                          type to the id of the schema it came
                                                          from

    Returns:
        Tuple[SubQueryNode, Set[str]]. The first element is the root of the tree of QueryNodes.
        Each node contains an AST representing a part of the overall query, targeting a
        specific schema. The second element is the set of all intermediate output names that are
        to be removed at the end

    Raises:
        GraphQLValidationError if the query doesn't validate against the schema, contains
        unsupported directives, or some property field occurs after a vertex field in some
        selection
    """
    _check_query_is_valid_to_split(merged_schema_descriptor.schema, query_ast)

    # If schema directives are correctly represented in the schema object, type_info is all
    # that's needed to detect and address stitching fields. However, before this issue is
    # fixed, it's necessary to use additional information from pre-processing the schema AST
    edge_to_stitch_fields = _get_edge_to_stitch_fields(merged_schema_descriptor)
    type_name_to_schema_id = merged_schema_descriptor.type_name_to_schema_id
    intermediate_out_name_assigner = IntermediateOutNameAssigner()

    root_query_node = SubQueryNode(query_ast)
    type_info = TypeInfo(merged_schema_descriptor.schema)
    query_nodes_to_split = [root_query_node]

    # Construct full tree of SubQueryNodes in a dfs pattern
    while len(query_nodes_to_split) > 0:
        current_node_to_split = query_nodes_to_split.pop()

        _split_query_one_level(current_node_to_split, type_info, edge_to_stitch_fields,
                               type_name_to_schema_id, intermediate_out_name_assigner)

        query_nodes_to_split.extend(
            child_query_connection.sink_query_node
            for child_query_connection in current_node_to_split.child_query_connections
        )

    return root_query_node, frozenset(intermediate_out_name_assigner.intermediate_output_names)


def _split_query_one_level(query_node, type_info, edge_to_stitch_fields, type_name_to_schema_id,
                           intermediate_out_name_assigner):
    """Modify query_node to have new children and new query ast

    The AST contained in the query_node will not be modified, just replaced by a new, different
    AST.
    """
    root_selection_ast = get_only_query_definition(query_node.query_ast)  # OperationDefinition
    root_selections = [root_selection_ast]
    type_info.enter(root_selection_ast)

    new_root_selections = _split_query_ast_recursive(
        query_node, root_selection_ast, root_selections, type_info, edge_to_stitch_fields,
        type_name_to_schema_id, intermediate_out_name_assigner
    )
    query_node.query_ast = ast_types.Document(
        definitions=new_root_selections
    )
    if query_node.schema_id is None:
        raise AssertionError(
            u'Unreachable code reached. The schema id of query piece "{}" has not been '
            u'determined.'.format(query_node.query_ast)
        )
    assert(query_node.schema_id is not None)
    type_info.leave(root_selection_ast)


def _split_query_ast_recursive(query_node, ast, parent_selections, type_info,
                               edge_to_stitch_fields, type_name_to_schema_id,
                               intermediate_out_name_assigner):
    """Always return Node, let the next level deal with sorting the output.

    child not modify parent list

    parent_selections contains all property fields in the previous level of fields, but not
    necessarily all fields (some edge fields may not be added)

    query_node's children are modified, intermediate_out_name_assigner may have new names, no
    other inputs are modified
    """
    # Wait, I need to reassign query_node's AST as well? Yeah I do
    # Check if split here, if so, split AST, make child query node, return property field
    if isinstance(ast, ast_types.Field):
        child_type = type_info.get_type()  # GraphQLType
        if child_type is None:
            raise SchemaStructureError(
                u'The provided merged schema descriptor may be invalid.'
            )
        while isinstance(child_type, (GraphQLList, GraphQLNonNull)):  # Unwrap List and NonNull
            child_type = child_type.of_type
        child_type_name = child_type.name

        edge_field_name = ast.name.value
        if (child_type_name, edge_field_name) in edge_to_stitch_fields:
            parent_field_name, child_field_name = \
                edge_to_stitch_fields[(child_type_name, edge_field_name)]
            # Deal with parent
            # Get field with existing directives
            parent_property_field = _get_property_field_to_return(
                parent_selections, parent_field_name, ast.directives
            )
            # Add @output if needed, record out_name
            parent_output_name = _get_out_name_optionally_add_output(
                parent_property_field, intermediate_out_name_assigner
            )
            # parent selections isn't modified until level above

            # Create child query node around ast
            child_query_node, child_output_name = _get_child_query_node_and_out_name(
                ast, type_info, child_field_name, intermediate_out_name_assigner
            )

            # Create and add QueryConnections
            _add_query_connections(
                query_node, child_query_node, parent_output_name, child_output_name
            )

            return parent_property_field
        else:
            # Check schema id matched
            # TODO: do the same to type coercions?
            # This part should be taken out to its own part
            _check_or_set_schema_id(query_node, child_type_name, type_name_to_schema_id)

    # No split here
    selections = ast.selection_set.selections
    if selections is None:  # Nothing to recurse on
        return ast

    type_info.enter(ast.selection_set)
    new_selections = []
    made_changes = False

    for selection in selections:  # Recurse on children
        type_info.enter(selection)
        # NOTE: By the time we reach any cross schema edge fields, new_selections contains all
        # property fields, including any new property fields created by previous cross schema
        # edge fields
        new_selection = _split_query_ast_recursive(query_node, selection, new_selections,
                                                   type_info, edge_to_stitch_fields,
                                                   type_name_to_schema_id,
                                                   intermediate_out_name_assigner)

        if new_selection is not selection:
            made_changes = True
            if _is_property_field(new_selection):
                # If a property field is returned and is different from the input, then this is
                # a property field used in stitching. If no existing field has this name, insert
                # the new property field to end of property fields. If some existing field has
                # this name, replace the existing field with the returned field
                new_selections = _replace_or_insert_property_field(new_selections, new_selection)
                # The current actual selection is ignored, edge field leading to a branch that
                # will not be added to the output tree
            else:
                # Changes were made somewhere down the line, append changed version to end
                new_selections.append(new_selection)
        else:
            new_selections.append(new_selection)
        type_info.leave(selection)
    type_info.leave(ast.selection_set)

    if made_changes:
        ast_copy = copy(ast)
        ast_copy.selections = new_selections
        return ast_copy
    else:
        return ast


def _check_or_set_schema_id(query_node, type_name, type_name_to_schema_id):
    """Set the schema id of the root node if not yet set, otherwise check schema ids agree.

    Args:
        type_name: str, name of the type whose schema id we're comparing against the
                   previously recorded schema id
    """
    if type_name in type_name_to_schema_id:  # It may be a scalar, and thus not found
        current_type_schema_id = type_name_to_schema_id[type_name]
        prior_type_schema_id = query_node.schema_id
        if prior_type_schema_id is None:  # First time checking schema_id
            query_node.schema_id = current_type_schema_id
        elif current_type_schema_id != prior_type_schema_id:
            # A single query piece has types from two schemas -- merged_schema_descriptor
            # is invalid: an edge field without a @stitch directive crosses schemas,
            # or type_name_to_schema_id is wrong
            raise SchemaStructureError(
                u'The provided merged schema descriptor may be invalid. Perhaps '
                u'some edge that does not have a @stitch directive crosses schemas. As '
                u'a result, query piece "{}", which is in the process of being broken '
                u'down, appears to contain types from more than one schema. Type "{}" '
                u'belongs to schema "{}", while some other type belongs to schema "{}".'
                u''.format(print_ast(query_node.query_ast), type_name,
                           current_type_schema_id, prior_type_schema_id)
            )


def _get_child_query_node_and_out_name(ast, type_info, child_field_name,
                                       intermediate_out_name_assigner):
    """Create a query node out of ast, return node and unique out_name on field with input name.

    Create a new document out of the input AST, that has the same structure as the input. For
    instance, if the input AST can be represented by
        out_Human {
          name
        }
    where out_Human is a vertex edge going to type Human, the resulting document will be
        {
          Human {
            name
          }
        }
    If the input AST starts with a type coercion, the resulting document will start with the
    coerced type, rather than the original union or interface type.

    The output child_node will be wrapped around this new Document. In addition, if no field
    of child_field_name currently exists, such a field will be added. If there is no @output
    directive on this field, a new @output directive will be added.

    Args:
        ast: type Node, representing the AST that we're using to build a child node. It is not
             modified by this function
        type_info: TypeInfo, at the location of the ast
        child_field_name: str. If no field of this name currently exists as a part of the root
                          selections of the input AST, a new field will be created in the AST
                          contained in the output child query node
        intermediate_out_name_assigner: IntermediateOutNameAssigner, which will be used to
                                        generate an out_name, if it's necessary to create a
                                        new @output directive

    Returns:
        Tuple[SubQueryNode, str], the child sub query node wrapping around the input ast, and
        the out_name of the @output directive uniquely identifying the field used or stitching
        in this sub query node
    """
    child_type_name, child_selections = _get_child_type_and_selections(ast, type_info)
    # Get existing field with name in child
    child_property_field = _get_property_field_to_return(child_selections, child_field_name, [])
    # Add @output if needed, record out_name
    child_output_name = _get_out_name_optionally_add_output(
        child_property_field, intermediate_out_name_assigner
    )
    # Get new child_selections
    child_selections = _replace_or_insert_property_field(child_selections, child_property_field)
    # Wrap around
    child_query_ast = _create_query_document(child_type_name, child_selections)
    child_query_node = SubQueryNode(child_query_ast)

    return child_query_node, child_output_name


def _get_property_field_to_return(selections, field_name, directives_from_edge):
    """Return a Field object with field_name, sharing directives with any such existing field.

    The new field will contain all valid directives in directives_on_edge.
    If there is an existing Field in parent_selection with field_name, the returned new Field
    will also contain all directives of the existing field with that name.
    """
    new_field = ast_types.Field(
        name=ast_types.Name(value=field_name),
        directives=[],
    )

    # Check parent_selection for existing field of given name
    parent_field = try_get_ast(selections, field_name, ast_types.Field)
    if parent_field is not None:
        # Existing field, add all its directives
        directives_from_existing_field = parent_field.directives
        if directives_from_existing_field is not None:
            new_field.directives.extend(directives_from_existing_field)

    # Transfer directives from edge
    if directives_from_edge is not None:
        for directive in directives_from_edge:
            if directive.name.value == u'output':  # output is illegal on edge field
                raise GraphQLValidationError(
                    u'Directive "{}" is not allowed on an edge field, as @output directives '
                    u'can only exist on property fields.'.format(directive)
                )
            elif directive.name.value == u'optional':
                if try_get_ast(new_field.directives, u'optional', ast_types.Directive) is None:
                    # New optional directive
                    new_field.directives.append(directive)
            elif directive.name.value == u'filter':
                new_field.directives.append(directive)
            elif directive.name.value == u'stitch':
                continue
            else:
                raise AssertionError(
                    u'Unreachable code reached. Directive "{}" is of an unsupported type, and '
                    u'was not caught in a prior validation step.'.format(new_directive)
                )

    return new_field


def _get_child_type_and_selections(ast, type_info):
    """Get the type (root field) and selection set of the input AST.

    For instance, if the root of the AST is a vertex field that goes to type Animal, the
    returned type name will be Animal.

    If the input AST is a type coercion, the root field name will be the coerced type rather
    than the union or interface type, and the selection set will contain actual fields
    rather than a single inline fragment.

    Args:
        ast: type Node, the AST that, if split off into its own Document, would have the the
             type (named the same as the root vertex field) and root selections that this
             function outputs
        type_info: TypeInfo, what is used to check for the type that 

    Returns:
        Tuple[str, List[Union[Field, InlineFragment]]], name and selections of the root
        vertex field of the input AST if it were made into its own separate Document
    """
    child_type = type_info.get_type()  # GraphQLType
    if child_type is None:
        raise SchemaStructureError(
            u'The provided merged schema descriptor may be invalid, as the type '
            u'corresponding to the field "{}" under type "{}" cannot be '
            u'found.'.format(ast.name.value, type_info.get_parent_type())
        )
    while isinstance(child_type, (GraphQLList, GraphQLNonNull)):  # Unwrap List and NonNull
        child_type = child_type.of_type
    child_type_name = child_type.name

    child_selection_set = ast.selection_set
    # Adjust for type coercion
    if (
        child_selection_set is not None and
        len(child_selection_set.selections) == 1 and
        isinstance(child_selection_set.selections[0], ast_types.InlineFragment)
    ):
        type_coercion_inline_fragment = child_selection_set.selections[0]
        child_type_name = type_coercion_inline_fragment.type_condition.name.value
        child_selection_set = type_coercion_inline_fragment.selection_set

    return child_type_name, child_selection_set.selections


def _check_query_is_valid_to_split(schema, query_ast):
    """Check the query is valid for splitting.

    In particular, ensure that the query validates against the schema, does not contain
    unsupported directives, and that in each selection, all property fields occur before all
    vertex fields.

    Args:
        schema: GraphQLSchema object
        query_ast: Document

    Raises:
        GraphQLValidationError if the query doesn't validate against the schema, contains
        unsupported directives, or some property field occurs after a vertex field in some
        selection
    """
    # Check builtin errors
    built_in_validation_errors = validate(schema, query_ast)
    if len(built_in_validation_errors) > 0:
        raise GraphQLValidationError(
            u'AST does not validate: {}'.format(built_in_validation_errors)
        )

    # Check no bad directives and fields are in order
    visitor = CheckQueryIsValidToSplit()
    visit(query_ast, visitor)


class CheckQueryIsValidToSplit(Visitor):
    """Check the query only has supported directives, and its fields are correctly ordered."""

    supported_directives = frozenset(('filter', 'output', 'optional', 'stitch'))
    # This is pretty restrictive, tags that don't cross boundaries are actually ok, but
    # figure out later

    def enter_Directive(self, node, *args):
        """Check that the directive is supported."""
        if node.name.value not in self.supported_directives:
            raise GraphQLValidationError(
                u'Directive "{}" is not yet supported, only "{}" are currently '
                u'supported.'.format(node.name.value, self.supported_directives)
            )

    def enter_SelectionSet(self, node, *args):
        """Check property fields occur before vertex fields and type coercions in selection."""
        past_property_fields = False  # Whether we're seen a vertex field
        for field in node.selections:
            if _is_property_field(field):
                if past_property_fields:
                    raise GraphQLValidationError(
                        u'In the selections {}, the property field {} occurs after a vertex '
                        u'field or a type coercion statement, which is not allowed, as all '
                        u'property fields must appear before all vertex fields.'.format(
                            node.selections, field
                        )
                    )
            else:
                past_property_fields = True


def _is_property_field(selection):
    """Return True if selection is a property field, False if a vertex field or type coercion."""
    if isinstance(selection, ast_types.InlineFragment):
        return False
    if isinstance(selection, ast_types.Field):
        if (
            selection.selection_set is None or
            selection.selection_set.selections is None or
            selection.selection_set.selections == []
        ):
            return True
        else:
            return False
    else:
        raise AssertionError(
            u'Input field "{}" is not of type Field or InlineFragment.'.format(selection)
        )


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
                stitch_directive = try_get_ast(
                    field_definition.directives, u'stitch', ast_types.Directive
                )
                if stitch_directive is not None:
                    source_field_name = stitch_directive.arguments[0].value.value
                    sink_field_name = stitch_directive.arguments[1].value.value
                    edge = (type_definition.name.value, field_definition.name.value)
                    edge_to_stitch_fields[edge] = (source_field_name, sink_field_name)

    return edge_to_stitch_fields


def _replace_or_insert_property_field(selections, new_field):
    """Return a copy of the input selections, with new_field added or replacing existing field.

    If there is an existing field with the same name as new_field, replace. Otherwise, insert
    new_field after the last existing property field.

    Inputs not modified.

    Args:
        selections: List[Union[Field, InlineFragment]], where all property fields occur
                    before all vertex fields and inline fragments
        new_field: Field object, to be inserted into selections

    Returns:
        List[Union[Field, InlineFragment]]
    """
    selections = copy(selections)
    for index, selection in enumerate(selections):
        if (
            isinstance(selection, ast_types.Field) and
            selection.name.value == new_field.name.value
        ):
            selections[index] = new_field
            return selections
        if not _is_property_field(selection):
            selections.insert(index, new_field)
            return selections


def _add_query_connections(parent_query_node, child_query_node, parent_field_output_name,
                           child_field_output_name):
    """Modify parent and child SubQueryNodes by adding QueryConnections between them."""
    # Create QueryConnections
    new_query_connection_from_parent = QueryConnection(
        sink_query_node=child_query_node,
        source_field_output_name=parent_field_output_name,
        sink_field_output_name=child_field_output_name,
    )
    new_query_connection_from_child = QueryConnection(
        sink_query_node=parent_query_node,
        source_field_output_name=child_field_output_name,
        sink_field_output_name=parent_field_output_name,
    )
    # Add QueryConnections
    parent_query_node.child_query_connections.append(new_query_connection_from_parent)
    child_query_node.parent_query_connection = new_query_connection_from_child


def _create_query_document(root_vertex_field_name, root_selections):
    """Return a Document representing a query with the specified name and selections."""
    return ast_types.Document(
        definitions=[
            ast_types.OperationDefinition(
                operation='query',
                selection_set=ast_types.SelectionSet(
                    selections=[
                        ast_types.Field(
                            name=ast_types.Name(value=root_vertex_field_name),
                            # NOTE: if the root_vertex_field_name does not actually exist
                            # as a root field (not all types are required to have a
                            # corresponding root vertex field), then this query will be
                            # invalid
                            selection_set=ast_types.SelectionSet(
                                selections=root_selections,
                            ),
                            directives=[],
                        )
                    ]
                )
            )
        ]
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


def _get_out_name_optionally_add_output(field, intermediate_out_name_assigner):
    """Return out_name of @output on field, creating new @output if needed.

    Args:
        field: Field object, whose directives we may modify
    """
    # Check for existing directive
    output_directive = try_get_ast(field.directives, u'output', ast_types.Directive)
    if output_directive is None:
        # Create and add new directive to field
        out_name = intermediate_out_name_assigner.assign_and_return_out_name()
        output_directive = _get_output_directive(out_name)
        if field.directives is None:
            field.directives = []
        field.directives.append(output_directive)  # TODO: modification!
        return out_name
    else:
        return output_directive.arguments[0].value.value  # Location of value of out_name
