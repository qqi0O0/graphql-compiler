

def demangle_query(query_string, renamed_schema):
    """Demangle all types in query_string from renames to originals.

    Args:
        query_string: str
        renamed_schema: RenamedSchema, namedtuple containing the ast of the renamed schema, and
                        a map of renamed names to original names

    Raises:
        Some other error

    Returns:
        query string where type names are demangled
    """
    ast = parse(query_string)
    # need to translate back both root fields and types. how to distinguish?
    # for example, maybe 'human: Human' got renamed to 'NewHuman: NewHuman' for some reason,
    # which is perfectly legal. Which one does NewHuman mean?
    # is it only the root of the query that can be a root field?
    # some fields are not translated, such as alias or various non-root field names
    visitor = DemangleQueryVisitor(self.reverse_name_id_map, self.reverse_root_field_id_map,
                                   schema_identifier)
    visit(ast, visitor)
    return print_ast(ast)


class DemangleQueryVisitor(Visitor):
    def __init__(self, reverse_name_id_map, reverse_root_field_id_map, schema_identifier):
        pass

    # Want to rename two things: the first level selection set field names (root fields)
    # and NamedTypes (e.g. in fragments)
    # Should do those in two steps
    # TODO
    # First step doesn't need visitor. Just iterate over selection set like with dedup
    # Second step uses very simple visitor that transforms all NamedTypes that are not scalars
    # or builtins?
