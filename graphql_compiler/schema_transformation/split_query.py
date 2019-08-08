# Copyright 2019-present Kensho Technologies, LLC.
from collections import namedtuple
from copy import copy, deepcopy

from graphql import print_ast
from graphql.language import ast as ast_types
from graphql.language.visitor import TypeInfoVisitor, Visitor, visit, REMOVE
from graphql.type.definition import GraphQLList, GraphQLNonNull
from graphql.utils.type_info import TypeInfo
from graphql.validation import validate

from ..exceptions import GraphQLValidationError
from .utils import SchemaStructureError, try_get_ast, try_get_ast_and_index


QueryConnection = namedtuple(
    'QueryConnection', (
        'sink_query_node',  # SubQueryNode
        'source_field_path',
        # List[Union[int, str]], the attribute names or list indices used to access the property
        # field used in the stitch, starting from the root of the source AST
        'sink_field_path',
        # List[Union[int, str]], the attribute names or list indices used to access the property
        # field used in the stitch, starting from the root of the sink AST
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
        SubQueryNode, the root of the tree of QueryNodes. Each node contains an AST
        representing a part of the overall query, targeting a specific schema

    Raises:
        GraphQLValidationError if the query doesn't validate against the schema, contains
        unsupported directives, or some property field occurs after a vertex field in some
        selection
    """
    _check_query_is_valid_to_split(merged_schema_descriptor.schema, query_ast)

    query_ast = deepcopy(query_ast)
    # If schema directives are correctly represented in the schema object, type_info is all
    # that's needed to detect and address stitching fields. However, before this issue is
    # fixed, it's necessary to use additional information from pre-processing the schema AST
    edge_to_stitch_fields = _get_edge_to_stitch_fields(merged_schema_descriptor)

    root_query_node = SubQueryNode(query_ast)
    type_info = TypeInfo(merged_schema_descriptor.schema)
    query_nodes_to_visit = [root_query_node]

    # Construct full tree of SubQueryNodes in a dfs pattern
    while len(query_nodes_to_visit) > 0:
        current_node_to_visit = query_nodes_to_visit.pop()
        split_query_visitor = SplitQueryVisitor(
            type_info, edge_to_stitch_fields, merged_schema_descriptor.type_name_to_schema_id,
            current_node_to_visit
        )
        visitor = TypeInfoVisitor(type_info, split_query_visitor)
        # TODO: this is super confusing, `visit` both modifies in place and modifies output,
        # and only the output contains all the modifications we want
        # It also still fails?
        current_node_to_visit.query_ast = visit(current_node_to_visit.query_ast, visitor)
        query_nodes_to_visit.extend(
            child_query_connection.sink_query_node
            for child_query_connection in current_node_to_visit.child_query_connections
        )

    return root_query_node


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
    """Return True if field is a property field, False if a vertex field or a type coercion."""
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


class SplitQueryVisitor(Visitor):
    """Prune branches of AST and build SubQueryNodes during traversal."""
    def __init__(self, type_info, edge_to_stitch_fields, type_name_to_schema_id, root_query_node):
        """Create a SubQueryNode with one level of children from the visited AST.

        The visitor will modify the AST by cutting off branches where stitches occur, and
        modify the root_query_node by creating a SubQueryNode for every cut-off branch and
        adding these new SubQueryNodes to the root_query_node's list of children. Cut-off
        branches will not be visited.

        Args:
            type_info: TypeInfo
            edge_to_stitch_fields: Dict[Tuple[str, str], Tuple[str, str]], mapping
                                   (name of type, name of field representing the edge) to
                                   (source field name, sink field name)
            type_name_to_schema_id: Dict[str, str], mapping name of each type to the id of the
                                    schema it came from
            root_query_node: SubQueryNode, its query_ast and child_query_connections will be
                             modified
        """
        self.type_info = type_info
        self.edge_to_stitch_fields = edge_to_stitch_fields
        self.type_name_to_schema_id = type_name_to_schema_id
        self.root_query_node = root_query_node

    # TODO: enter_SelectionSet instead? Much more freedom and control over the selections list
    def enter_Field(self, node, key, parent, path, *args):
        """Check for split at the current field, creating a new SubQueryNode if needed.

        If there is a new split at this field as clued by a @stitch directive, a new AST
        will be created from the current branch, and the branch will be removed from the AST
        being visited. If the property field used in the stitch is not present, it will be
        added to the new AST. A new SubQueryNode will be created around this new AST, and
        be added to the list of children of root_query_node. The rest of the branch will
        not be visited.

        A newly added property field will be placed between existing property fields and
        existing vertex fields.

        Args:
            node: Field that is being visited
            key: int, index of the current node in the parent list
            parent: List[Union[Field, InlineFragment]], containing all other fields or type
                    coercions in this selection
            path: List[Union[int, str]], listing the attribute names or list indices used to
                  index into the AST, starting from the root, to reach the current node
        """
        print(node.name.value)
        def p(child):
            if child is None:
                return None
            return child.name.value
        print([p(child) for child in parent])
        # Get root vertex field name and selection set of the current branch of the AST
        child_type_name, child_selection_set = \
            self._get_child_root_vertex_field_name_and_selection_set(node)

        # Get the tuple used as key into dict of property fields used in stitch
        type_name_field_name = (self.type_info.get_parent_type().name, node.name.value)

        if type_name_field_name not in self.edge_to_stitch_fields:  # No stitch at this field
            # The type at the end of the edge doesn't cross schemas, check its schema id
            self._check_or_set_schema_id(child_type_name)
            return

        if child_selection_set is None:
            raise SchemaStructureError(
                u'The edge "{}" is unexpectedly a property field with no further selection '
                u'set, but edges marked with @stitch must be vertex fields, connecting '
                u'vertices between schemas.'.format(node)
            )

        parent_field_name, child_field_name = self.edge_to_stitch_fields[type_name_field_name]
        # Get path to the property fields used in stitching, creating new fields if needed
        parent_field_path = self._process_parent_field_get_field_path(
            node, key, parent, path, parent_field_name
        )
        child_field_path = self._process_child_field_get_field_path(
            child_selection_set.selections, child_field_name
        )

        # Create child AST around the pruned branch, and child SubQueryNode around the AST
        child_query_ast = _create_query_document(child_type_name, child_selection_set)
        child_query_node = SubQueryNode(child_query_ast)
        # Create and add QueryConnections to parent and child
        _add_query_connections(self.root_query_node, child_query_node, parent_field_path,
                               child_field_path)

        print([p(child) for child in parent])
        if parent[key] is None:
            # NOTE: this doesn't quite work -- None isn't deleted until all siblings have been
            # visited, at which point the siblings have the wrong indices
            return REMOVE  # Delete branch (delete the None without affecting visitor traversal)
        else:
            return False  # Skip visiting the branch

    def _check_or_set_schema_id(self, type_name):
        """Set the schema id of the root node if not yet set, otherwise check schema ids agree.

        Args:
            type_name: str, name of the type whose schema id we're comparing against the
                       previously recorded schema id
        """
        if type_name in self.type_name_to_schema_id:  # It may be a scalar, and thus not found
            current_type_schema_id = self.type_name_to_schema_id[type_name]
            prior_type_schema_id = self.root_query_node.schema_id
            if prior_type_schema_id is None:  # First time checking schema_id
                self.root_query_node.schema_id = current_type_schema_id
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
                    u''.format(print_ast(self.root_query_node.query_ast), type_name,
                               current_type_schema_id, prior_type_schema_id)
                )

    def _get_child_root_vertex_field_name_and_selection_set(self, node):
        """Get the root field name and selection set of the child AST split at the input node.

        Takes care of type coercion, so the root field name will be the coerced type rather than
        a, say, union type, and the selection set will contain real fields rather than a single
        inline fragment.

        node must be the node that the visitor is currently on, to ensure that self.type_info
        matches up with node.

        Args:
            node: Field, the node that the visitor is currently on

        Returns:
            Tuple[str, SelectionSet or None], name and selection set of the root vertex field
            of the child branch of the AST cut off at node
        """
        child_type = self.type_info.get_type()  # GraphQLType
        if child_type is None:
            raise SchemaStructureError(
                u'The provided merged schema descriptor may be invalid, as the type '
                u'corresponding to the field "{}" under type "{}" cannot be '
                u'found.'.format(node.name.value, self.type_info.get_parent_type())
            )
        while isinstance(child_type, (GraphQLList, GraphQLNonNull)):  # Unwrap List and NonNull
            child_type = child_type.of_type
        child_type_name = child_type.name
        child_selection_set = node.selection_set

        # Adjust for type coercion
        if (
            child_selection_set is not None and
            len(child_selection_set.selections) == 1 and
            isinstance(child_selection_set.selections[0], ast_types.InlineFragment)
        ):
            type_coercion_inline_fragment = child_selection_set.selections[0]
            child_type_name = type_coercion_inline_fragment.type_condition.name.value
            child_selection_set = type_coercion_inline_fragment.selection_set

        return child_type_name, child_selection_set

    def _process_parent_field_get_field_path(self, node, key, parent, path, parent_field_name):
        """Modify fields, return path to parent property field used to stitch.

        If a property field with the specified name already exists, return a path to this field,
        and replace the current node by None to be deleted later.
        If not, create a new property field with the specified name, insert it after all
        existing property fields, remove the current node, and return the path to the newly
        added field.

        Args:
            node: Field, the node that we're currently on
            key: int, the index of the node in parent
            parent: List[Union[Field, InlineFragment]], a list of fields and type coercions
                    containing the current node. We search for a property field with the
                    input field name in this list, and modify this list as we insert new fields,
                    and replace or remove existing fields.
            path: List[Union[int, str]], listing the attribute names or list indices used to
                  index into the AST, starting from the root, to reach the current node
            parent_field_name: str, the name of the property field we're searching for in
                               parent

        Returns:
            List[Union[int, str]], listing the attribute names of list indices used to index
            into the ast, starting at the root, to reach the property field used in stitching
        """
        # Check for existing field in parent
        parent_field, parent_field_index = try_get_ast_and_index(
            parent, parent_field_name, ast_types.Field
        )
        # Process parent field, and get parent field path
        if parent_field is None:  # No existing source property field
            # Delete current field, add new property field.
            #
            # The new property field must occur before all existing vertex fields due to
            # the compiler's requirements. It should also not affect the index of existing
            # property fields, since such fields may have been used in previous stitching
            # edges, and their paths, which includes their index in the list, would become
            # invalid if the positions of these property fields changed. Thus, the new field
            # will be added between all existing property fields and all existing vertex fields
            #
            # Since the new field will be added before or at the location of the current field,
            # which will be removed, the part of the list of selections after the current field
            # will be unaffected, and the visitor's traversal continues as normal
            parent_field = ast_types.Field(
                name=ast_types.Name(value=parent_field_name)
            )
            parent.pop(key)  # Delete current field
            parent_field_index = _insert_new_property_field(parent, parent_field)
        else:
            # Remove stump field. Deleting the field directly affects the visitor's traversal,
            # so replace this node by None here, and return REMOVE at the end of enter_Field
            parent[key] = None

        # Valid existing directives are passed down
        self._add_directives_from_edge(parent_field, node.directives)
        # Get field path
        parent_field_path = copy(path)
        parent_field_path[-1] = parent_field_index  # Change last (current) index
        return parent_field_path

    def _process_child_field_get_field_path(self, child_selections, child_field_name):
        """Create new field if needed, return path to parent property field used to stitch.

        Args:
            child_selections: List[Union[Field, InlineFragment]], a list of fields and type
                              coercions, where we search for a property field with the input
                              field name. We may modify this list by inserting a new field
                              if the property field is not found
            child_field_name: str, the name of the property field we're searching for in
                              child_selections

        Returns:
            List[Union[int, str]], listing the attribute names of list indices used to index
            into the ast, starting at the root, to reach the property field used in stitching
        """
        # Check for existing field in child
        child_field, child_field_index = try_get_ast_and_index(
            child_selections, child_field_name, ast_types.Field
        )
        # Process child field, and get child field path
        if child_field is None:
            # Add new field to child's selection set, between all existing property fields
            # and all existing vertex fields
            child_field = ast_types.Field(
                name=ast_types.Name(value=child_field_name)
            )
            child_field_index = _insert_new_property_field(child_selections, child_field)

        child_field_path = [
            'definitions', 0, 'selection_set', 'selections', 0, 'selection_set',
            'selections', child_field_index
        ]
        return child_field_path

    def _add_directives_from_edge(self, field, new_directives):
        """Add new directives to field as necessary.

        new_directives comes from a cross schema edge. Thus, @output directives are disallowed,
        and @stitch directives are ignored, when adding directives onto the new field.

        Args:
            field: Field object, a property field, whose directives attribute will be modified
            new_directives: List[Directive] or None, directives previously existing on an
                            cross schema edge field
        """
        if new_directives is None:  # Nothing to add
            return
        if field.directives is None:
            field.directives = []
        for new_directive in new_directives:
            if new_directive.name.value == u'output':  # output is illegal on edge field
                raise GraphQLValidationError(
                    u'Directive "{}" is not allowed on an edge field, as @output directives '
                    u'can only exist on property fields.'.format(new_directive)
                )
            elif new_directive.name.value == u'optional':
                if try_get_ast(field.directives, u'optional', ast_types.Directive) is None:
                    # New optional directive
                    field.directives.append(new_directive)
            elif new_directive.name.value == u'filter':
                field.directives.append(new_directive)
            elif new_directive.name.value == u'stitch':
                continue
            else:
                raise AssertionError(
                    u'Unreachable code reached. Directive "{}" is of an unsupported type, and '
                    u'was not caught in a prior validation step.'.format(new_directive)
                )

    def leave_Document(self, node, *args):
        # Confirm that schema_id has been filled in
        if self.root_query_node.schema_id is None:
            raise AssertionError(
                u'Unreachable code reached. The schema id of query piece "{}" has not been '
                u'determined.'.format(print_ast(self.root_query_node.query_ast))
            )


def _insert_new_property_field(selections, new_field):
    """Insert new_field into selections, between existing property fields and vertex fields.

    In selections, all property fields, if any, must occur before all vertex fields, if any.

    Args:
        selections: List[Field], where all property fields occur before all vertex fields.
                    Modified by this function
        new_field: Field object, to be inserted into selections

    Returns:
        int, the index where the new field was inserted
    """
    index_to_insert = None
    for index, selection in enumerate(selections):
        if _is_property_field(selection):
            if index_to_insert is not None:
                raise AssertionError(
                    u'Property field {} comes after some vertex field in selection {}, and '
                    u'this was not caught in a prior valiation step.'.format(
                        selection, selections
                    )
                )
        else:
            if index_to_insert is None:
                index_to_insert = index
    if index_to_insert is None:  # No vertex fields
        index_to_insert = len(selections)
    selections.insert(index_to_insert, new_field)
    return index_to_insert


def _add_query_connections(parent_query_node, child_query_node, parent_field_path,
                           child_field_path):
    """Modify parent and child SubQueryNodes by adding QueryConnections between them."""
    # Create QueryConnections
    new_query_connection_from_parent = QueryConnection(
        sink_query_node=child_query_node,
        source_field_path=parent_field_path,
        sink_field_path=child_field_path,
    )
    new_query_connection_from_child = QueryConnection(
        sink_query_node=parent_query_node,
        source_field_path=child_field_path,
        sink_field_path=parent_field_path,
    )
    # Add QueryConnections
    parent_query_node.child_query_connections.append(new_query_connection_from_parent)
    child_query_node.parent_query_connection = new_query_connection_from_child


def _create_query_document(root_vertex_field_name, root_selection_set):
    """Return a Document representing a query with the specified name and selection set."""
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
                            selection_set=root_selection_set,
                            directives=[],
                        )
                    ]
                )
            )
        ]
    )
