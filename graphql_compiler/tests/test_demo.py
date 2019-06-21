# Copyright 2017-present Kensho Technologies, LLC.
import sqlalchemy
import six
import unittest
from .test_helpers import get_schema, get_sql_metadata, compare_sql
from ..compiler import compiler_frontend, blocks, helpers, expressions


def split_blocks(ir_blocks):
    if not isinstance(ir_blocks[0], blocks.QueryRoot):
        raise AssertionError(u'TODO')

    start_classname = helpers.get_only_element_from_collection(ir_blocks[0].start_class)
    local_operations = []
    found_global_operations_block = False
    global_operations = []
    for block in ir_blocks[1:]:
        if isinstance(block, blocks.QueryRoot):
            raise AssertionError(u'TODO')
        elif isinstance(block, blocks.GlobalOperationsStart):
            if found_global_operations_block:
                raise AssertionError(u'TODO')
            found_global_operations_block = True
        if found_global_operations_block:
            global_operations.append(block)
        else:
            local_operations.append(block)
    return start_classname, local_operations, global_operations


def emit_sql(ir, tables, sql_edges):
    """Emit SQLAlchemy from IR.

    Args:
        - ir: IR
        - tables: dict from graphql vertex names to sqlalchemy tables. The tables can come from different
          metadatas, and live in different tables, it doesn't really matter. If they do come from different
          databases, their table.schema should contain '<database_name>.<schema_name>'.
        - sql_edges: dict mapping graphql classes to:
                        dict mapping edge fields at that class to a dict with the following info:
                           to_table: GrapqQL vertex where the edge ends up
                           from_column: column name in this table
                           to_column: column name in tables[to_table]. The join is done on the from_column
                                      and to_column being equal. If you really need other kinds of joins,
                                      feel free to extend the interface.
    """
    current_classname, local_operations, global_operations = split_blocks(ir.ir_blocks)
    current_location = ir.query_metadata_table.root_location
    current_alias = tables[current_classname].alias()
    alias_at_location = {}  # Updated only at MarkLocation blocks

    from_clause = current_alias
    outputs = []
    filters = []

    for block in local_operations:
        if isinstance(block, (blocks.EndOptional)):
            pass  # Nothing to do
        elif isinstance(block, blocks.MarkLocation):
            alias_at_location[current_location] = current_alias
        elif isinstance(block, blocks.Backtrack):
            current_location = block.location
            current_alias = alias_at_location[current_location]
            current_classname = ir.query_metadata_table.get_location_info(current_location).type.name
        elif isinstance(block, blocks.Traverse):
            previous_alias = current_alias
            edge_field = u'{}_{}'.format(block.direction, block.edge_name)
            current_location = current_location.navigate_to_subpath(edge_field)
            edge = sql_edges[current_classname][edge_field]
            current_alias = tables[edge['to_table']].alias()
            current_classname = ir.query_metadata_table.get_location_info(current_location).type.name

            from_clause = from_clause.join(
                current_alias,
                onclause=(previous_alias.c[edge['from_column']] == current_alias.c[edge['to_column']]),
                isouter=block.optional)
        elif isinstance(block, blocks.Filter):
            # TODO check it works for filter inside optional.
            filters.append(block.predicate.to_sql(current_alias))
        else:
            raise NotImplementedError(u'{}'.format(block))

    current_location = None
    for block in global_operations:
        if isinstance(block, blocks.ConstructResult):
            for output_name, field in six.iteritems(block.fields):
                # import pdb; pdb.set_trace()

                # HACK for outputs in optionals
                if isinstance(field, expressions.TernaryConditional):
                    if isinstance(field.predicate, expressions.ContextFieldExistence):
                        field = field.if_true

                table = alias_at_location[field.location.at_vertex()]
                outputs.append(table.c.get(field.location.field).label(output_name))

    return sqlalchemy.select(outputs).select_from(from_clause).where(sqlalchemy.and_(*filters))


def compile_sql(schema, tables, sql_edges, graphql_string):
    ir = compiler_frontend.graphql_to_ir(schema, graphql_string)
    return emit_sql(ir, tables, sql_edges)


from sqlalchemy.dialects import mssql
class TestDemo(unittest.TestCase):
    def setUp(self):
        """Disable max diff limits for all tests."""
        self.maxDiff = None
        self.schema = get_schema()
        self.sqlalchemy_metadata, self.tables, self.sql_edges = get_sql_metadata()

    def test_simple_traversal(self):
        graphql_input = '''{
            Animal {
                out_Animal_ParentOf {
                    name @output(out_name: "child_name")
                }
            }
        }'''
        sql_query = compile_sql(
            self.schema,
            self.tables,
            self.sql_edges,
            graphql_input
        )
        sql_query = str(sql_query.compile(dialect=mssql.dialect()))
        expected_sql = '''
            SELECT
                [Animal_1].name AS child_name
            FROM [Animals].schema_1.[Animal] AS [Animal_2]
                JOIN [Animals].schema_1.[Animal] AS [Animal_1] ON [Animal_2].parent = [Animal_1].uuid
        '''
        compare_sql(self, expected_sql, sql_query)

    def test_multiple_traversals(self):
        graphql_input = '''{
            Animal {
                name @output(out_name: "animal_name")
                out_Animal_ParentOf {
                    name @output(out_name: "child_name")
                    out_Animal_ParentOf {
                        name @output(out_name: "grandchild_name")
                    }
                }
            }
        }'''
        sql_query = compile_sql(
            self.schema,
            self.tables,
            self.sql_edges,
            graphql_input
        )
        sql_query = str(sql_query.compile(dialect=mssql.dialect()))
        expected_sql = '''
            SELECT
                [Animal_1].name AS animal_name,
                [Animal_2].name AS child_name,
                [Animal_3].name AS grandchild_name
            FROM [Animals].schema_1.[Animal] AS [Animal_1]
                JOIN [Animals].schema_1.[Animal] AS [Animal_2] ON [Animal_1].parent = [Animal_2].uuid
                JOIN [Animals].schema_1.[Animal] AS [Animal_3] ON [Animal_2].parent = [Animal_3].uuid
        '''
        compare_sql(self, expected_sql, sql_query)

    def test_equals_filter(self):
        graphql_input = '''{
            Animal {
                uuid @filter(op_name: "=", value: ["$animal_uuid"])
                out_Animal_ParentOf {
                    name @output(out_name: "child_name")
                }
            }
        }'''
        sql_query = compile_sql(
            self.schema,
            self.tables,
            self.sql_edges,
            graphql_input
        )
        sql_query = str(sql_query.compile(dialect=mssql.dialect()))
        expected_sql = '''
            SELECT
                [Animal_1].name AS child_name
            FROM [Animals].schema_1.[Animal] AS [Animal_2]
                JOIN [Animals].schema_1.[Animal] AS [Animal_1] ON [Animal_2].parent = [Animal_1].uuid
            WHERE [Animal_2].uuid = :animal_uuid
        '''
        compare_sql(self, expected_sql, sql_query)

    def test_less_than_or_equal_filter(self):
        graphql_input = '''{
            Animal {
                net_worth @filter(op_name: "<=", value: ["$max_net_worth"])
                out_Animal_ParentOf {
                    name @output(out_name: "child_name")
                }
            }
        }'''
        sql_query = compile_sql(
            self.schema,
            self.tables,
            self.sql_edges,
            graphql_input
        )
        sql_query = str(sql_query.compile(dialect=mssql.dialect()))
        expected_sql = '''
            SELECT
                [Animal_1].name AS child_name
            FROM [Animals].schema_1.[Animal] AS [Animal_2]
                JOIN [Animals].schema_1.[Animal] AS [Animal_1] ON [Animal_2].parent = [Animal_1].uuid
            WHERE [Animal_2].net_worth <= :max_net_worth
        '''
        compare_sql(self, expected_sql, sql_query)

    def test_optional(self):
        graphql_input = '''{
            Animal {
                out_Animal_ParentOf @optional {
                    name @output(out_name: "child_name")
                }
            }
        }'''
        sql_query = compile_sql(
            self.schema,
            self.tables,
            self.sql_edges,
            graphql_input
        )
        sql_query = str(sql_query.compile(dialect=mssql.dialect()))
        expected_sql = '''
            SELECT
                [Animal_1].name AS child_name
            FROM [Animals].schema_1.[Animal] AS [Animal_2]
                LEFT OUTER JOIN [Animals].schema_1.[Animal] AS [Animal_1] ON [Animal_2].parent = [Animal_1].uuid
        '''
        compare_sql(self, expected_sql, sql_query)