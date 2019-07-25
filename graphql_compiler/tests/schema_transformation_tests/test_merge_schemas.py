# Copyright 2019-present Kensho Technologies, LLC.
from collections import OrderedDict
from textwrap import dedent
import unittest

from graphql import parse
from graphql.language.printer import print_ast

from graphql_compiler.schema_transformation.merge_schemas import (
    merge_schemas, CrossSchemaEdgeDescriptor, FieldReference
)
from graphql_compiler.schema_transformation.utils import (
    SchemaNameConflictError, InvalidCrossSchemaEdgeError
)

from .input_schema_strings import InputSchemaStrings as ISS


class TestMergeSchemasNoCrossSchemaEdges(unittest.TestCase):
    def test_basic_merge(self):
        merged_schema = merge_schemas(
            OrderedDict([
                ('basic', parse(ISS.basic_schema)),
                ('enum', parse(ISS.enum_schema)),
            ]),
            [],
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
            }

            type Human {
              id: String
            }

            type Droid {
              height: Height
            }

            enum Height {
              TALL
              SHORT
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))
        self.assertEqual({'Droid': 'enum', 'Height': 'enum', 'Human': 'basic'},
                         merged_schema.type_name_to_schema_id)

    def test_original_unmodified(self):
        basic_ast = parse(ISS.basic_schema)
        enum_ast = parse(ISS.enum_schema)
        merge_schemas(
            OrderedDict([
                ('basic', basic_ast),
                ('enum', enum_ast),
            ]),
            [],
        )
        self.assertEqual(basic_ast, parse(ISS.basic_schema))
        self.assertEqual(enum_ast, parse(ISS.enum_schema))

    def test_multiple_merge(self):
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.basic_schema)),
                ('second', parse(ISS.enum_schema)),
                ('third', parse(ISS.interface_schema)),
                ('fourth', parse(ISS.non_null_schema)),
            ]),
            [],
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
              Character: Character
              Kid: Kid
              Dog: Dog!
            }

            type Human {
              id: String
            }

            type Droid {
              height: Height
            }

            enum Height {
              TALL
              SHORT
            }

            interface Character {
              id: String
            }

            type Kid implements Character {
              id: String
            }

            type Dog {
              id: String!
              friend: Dog!
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_different_query_type_name_merge(self):
        different_query_type_schema = dedent('''\
            schema {
              query: RandomRootSchemaQueryName
            }

            type Droid {
              id: String
            }

            type RandomRootSchemaQueryName {
              Droid: Droid
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.basic_schema)),
                ('second', parse(different_query_type_schema)),
            ]),
            [],
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
            }

            type Human {
              id: String
            }

            type Droid {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_objects_merge_conflict(self):
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(ISS.basic_schema)),
                ]),
                [],
            )

    def test_interface_object_merge_conflict(self):
        interface_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            interface Human {
              id: String
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('basic', parse(ISS.basic_schema)),
                    ('bad', parse(interface_conflict_schema)),
                ]),
                [],
            )
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('bad', parse(interface_conflict_schema)),
                    ('basic', parse(ISS.basic_schema)),
                ]),
                [],
            )

    def test_enum_object_merge_conflict(self):
        enum_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            enum Human {
              CHILD
              ADULT
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('basic', parse(ISS.basic_schema)),
                    ('bad', parse(enum_conflict_schema)),
                ]),
                [],
            )
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('bad', parse(enum_conflict_schema)),
                    ('basic', parse(ISS.basic_schema)),
                ]),
                [],
            )

    def test_enum_interface_merge_conflict(self):
        enum_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            enum Character {
              FICTIONAL
              REAL
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('interface', parse(ISS.interface_schema)),
                    ('bad', parse(enum_conflict_schema)),
                ]),
                [],
            )
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('bad', parse(enum_conflict_schema)),
                    ('interface', parse(ISS.interface_schema)),
                ]),
                [],
            )

    def test_object_scalar_merge_conflict(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            scalar Human
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('basic', parse(ISS.basic_schema)),
                    ('bad', parse(scalar_conflict_schema)),
                ]),
                [],
            )
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('bad', parse(scalar_conflict_schema)),
                    ('basic', parse(ISS.basic_schema)),
                ]),
                [],
            )

    def test_interface_scalar_merge_conflict(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            scalar Character
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('interface', parse(ISS.interface_schema)),
                    ('bad', parse(scalar_conflict_schema)),
                ]),
                [],
            )
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('bad', parse(scalar_conflict_schema)),
                    ('interface', parse(ISS.interface_schema)),
                ]),
                [],
            )

    def test_enum_scalar_merge_conflict(self):
        scalar_conflict_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type SchemaQuery {
              Int: Int
            }

            scalar Height
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('enum', parse(ISS.enum_schema)),
                    ('bad', parse(scalar_conflict_schema)),
                ]),
                [],
            )
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('bad', parse(scalar_conflict_schema)),
                    ('enum', parse(ISS.enum_schema)),
                ]),
                [],
            )

    def test_dedup_scalars(self):
        extra_scalar_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            scalar Date

            scalar Decimal

            type Kid {
              height: Decimal
            }

            type SchemaQuery {
              Kid: Kid
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.scalar_schema)),
                ('second', parse(extra_scalar_schema)),
            ]),
            [],
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Kid: Kid
            }

            type Human {
              id: String
              birthday: Date
            }

            scalar Date

            scalar Decimal

            type Kid {
              height: Decimal
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))
        self.assertEqual({'Human': 'first', 'Kid': 'second'},
                         merged_schema.type_name_to_schema_id)

    def test_dedup_same_directives(self):
        extra_directive_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

            directive @output(out_name: String!) on FIELD

            type Kid {
              id: String
            }

            type SchemaQuery {
              Kid: Kid
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.directive_schema)),
                ('second', parse(extra_directive_schema)),
            ]),
            [],
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Droid: Droid
              Kid: Kid
            }

            type Human {
              id: String
            }

            type Droid {
              id: String
              friend: Human @stitch(source_field: "id", sink_field: "id")
            }

            directive @stitch(source_field: String!, sink_field: String!) on FIELD_DEFINITION

            directive @output(out_name: String!) on FIELD

            type Kid {
              id: String
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))
        self.assertEqual({'Human': 'first', 'Droid': 'first', 'Kid': 'second'},
                         merged_schema.type_name_to_schema_id)

    def test_clashing_directives(self):
        extra_directive_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            directive @stitch(out_name: String!) on FIELD

            type Kid {
              id: String
            }

            type SchemaQuery {
              Kid: Kid
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.directive_schema)),
                    ('second', parse(extra_directive_schema)),
                ]),
                [],
            )

    def test_invalid_identifiers(self):
        with self.assertRaises(ValueError):
            merge_schemas(
                OrderedDict([
                    ('', parse(ISS.basic_schema)),
                ]),
                [],
            )
        with self.assertRaises(ValueError):
            merge_schemas(
                OrderedDict([
                    ('hello\n', parse(ISS.basic_schema)),
                ]),
                [],
            )
        with self.assertRaises(ValueError):
            merge_schemas(
                OrderedDict([
                    ('<script>alert("hello world")</script>', parse(ISS.basic_schema)),
                ]),
                [],
            )
        with self.assertRaises(ValueError):
            merge_schemas(
                OrderedDict([
                    ('\t\b', parse(ISS.basic_schema)),
                ]),
                [],
            )


class TestMergeSchemasCrossSchemaEdgesWithoutSubclasses(unittest.TestCase):
    def test_simple_cross_schema_edge_descriptor(self):
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.basic_schema)),
                ('second', parse(ISS.same_field_schema)),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Human',
                        field_name = 'id',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Person',
                        field_name = 'identifier',
                    ),
                    out_edge_only=False,
                ),
            ]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Person: Person
            }

            type Human {
              id: String
              out_example_edge: [Person] @stitch(source_field: "id", sink_field: "identifier")
            }

            type Person {
              identifier: String
              in_example_edge: [Human] @stitch(source_field: "identifier", sink_field: "id")
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_original_unmodified_when_edges_added(self):
        basic_schema_ast = parse(ISS.basic_schema)
        same_field_schema_ast = parse(ISS.same_field_schema)
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', basic_schema_ast),
                ('second', same_field_schema_ast),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Human',
                        field_name = 'id',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Person',
                        field_name = 'identifier',
                    ),
                    out_edge_only=False,
                ),
            ]
        )
        self.assertEqual(ISS.basic_schema, print_ast(basic_schema_ast))
        self.assertEqual(ISS.same_field_schema, print_ast(same_field_schema_ast))

    def test_one_directional_cross_schema_edge_descriptor(self):
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.basic_schema)),
                ('second', parse(ISS.same_field_schema)),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Human',
                        field_name = 'id',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Person',
                        field_name = 'identifier',
                    ),
                    out_edge_only=True,
                ),
            ]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Person: Person
            }

            type Human {
              id: String
              out_example_edge: [Person] @stitch(source_field: "id", sink_field: "identifier")
            }

            type Person {
              identifier: String
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_multiple_fields_cross_schema_edge_descriptor(self):
        multiple_fields_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              age: Int
              name: String!
              identifier: String
              friends: [Person]
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.basic_schema)),
                ('second', parse(multiple_fields_schema)),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Human',
                        field_name = 'id',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Person',
                        field_name = 'identifier',
                    ),
                    out_edge_only=False,
                ),
            ]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Person: Person
            }

            type Human {
              id: String
              out_example_edge: [Person] @stitch(source_field: "id", sink_field: "identifier")
            }

            type Person {
              age: Int
              name: String!
              identifier: String
              friends: [Person]
              in_example_edge: [Human] @stitch(source_field: "identifier", sink_field: "id")
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_non_null_scalar_match_normal_scalar(self):
        non_null_field_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              identifier: String!
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.basic_schema)),
                ('second', parse(non_null_field_schema)),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Human',
                        field_name = 'id',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Person',
                        field_name = 'identifier',
                    ),
                    out_edge_only=False,
                ),
            ]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Person: Person
            }

            type Human {
              id: String
              out_example_edge: [Person] @stitch(source_field: "id", sink_field: "identifier")
            }

            type Person {
              identifier: String!
              in_example_edge: [Human] @stitch(source_field: "identifier", sink_field: "id")
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_matching_user_defined_scalar(self):
        additional_scalar_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              age: Int
              bday: Date
            }

            scalar Date

            type SchemaQuery {
              Person: Person
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.scalar_schema)),
                ('second', parse(additional_scalar_schema)),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Human',
                        field_name = 'birthday',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Person',
                        field_name = 'bday',
                    ),
                    out_edge_only=False,
                ),
            ]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Person: Person
            }

            type Human {
              id: String
              birthday: Date
              out_example_edge: [Person] @stitch(source_field: "birthday", sink_field: "bday")
            }

            scalar Date

            type Person {
              age: Int
              bday: Date
              in_example_edge: [Human] @stitch(source_field: "bday", sink_field: "birthday")
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))


class TestMergeSchemasInvalidCrossSchemaEdges(unittest.TestCase):
    def test_invalid_edge_within_single_schema(self):
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('schema', parse(ISS.union_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'schema',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'schema',
                            type_name = 'Droid',
                            field_name = 'id',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_nonexistent_schema(self):
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(ISS.same_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'third',
                            type_name = 'Person',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_type_in_wrong_schema(self):
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(ISS.same_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Person',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_nonexistent_type(self):
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(ISS.same_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Droid',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_scalar_type(self):
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(ISS.same_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'String',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Droid',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_enum_type(self):
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(ISS.enum_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Height',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_union_type(self):
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.union_schema)),
                    ('second', parse(ISS.interface_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'HumanOrDroid',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Kid',
                            field_name = 'id',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_nonexistent_field(self):
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(ISS.same_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'name',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_clash_with_existing_field(self):
        clashing_field_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              identifier: String
              in_clashing_name: Int
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(clashing_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'clashing_name',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_clash_with_previous_edge(self):
        with self.assertRaises(SchemaNameConflictError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(ISS.same_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'clashing_name',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'clashing_name',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_field_not_scalar_type(self):
        not_scalar_field_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              friend: Person
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(not_scalar_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'clashing_name',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'friend',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_field_list_of_types(self):
        not_scalar_field_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              friend: [Person]
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(not_scalar_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'clashing_name',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'friend',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_field_list_of_scalars(self):
        not_scalar_field_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              id: [String]
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(not_scalar_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'clashing_name',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'id',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_field_non_null_type(self):
        not_scalar_field_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              friend: Person!
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(not_scalar_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'clashing_name',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'friend',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_field_mismatched_scalar(self):
        mismatched_scalar_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              identifier: Int
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(mismatched_scalar_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'clashing_name',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )

    def test_invalid_edge_non_null_scalar_mismatch_normal_scalar(self):
        non_null_field_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            type Person {
              identifier: Int!
            }

            type SchemaQuery {
              Person: Person
            }
        ''')
        with self.assertRaises(InvalidCrossSchemaEdgeError):
            merge_schemas(
                OrderedDict([
                    ('first', parse(ISS.basic_schema)),
                    ('second', parse(non_null_field_schema)),
                ]),
                [
                    CrossSchemaEdgeDescriptor(
                        edge_name = 'example_edge',
                        outbound_side = FieldReference(
                            schema_id = 'first',
                            type_name = 'Human',
                            field_name = 'id',
                        ),
                        inbound_side = FieldReference(
                            schema_id = 'second',
                            type_name = 'Person',
                            field_name = 'identifier',
                        ),
                        out_edge_only=False,
                    ),
                ]
            )


class TestMergeSchemasCrossSchemaEdgesWithSubclasses(unittest.TestCase):
    def test_edge_outbound_side_interface(self):
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.basic_schema)),
                ('second', parse(ISS.interface_with_subclasses_schema)),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Human',
                        field_name = 'id',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Individual',
                        field_name = 'ID',
                    ),
                    out_edge_only=False,
                ),
            ]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Individual: Individual
              President: President
            }

            type Human {
              id: String
              out_example_edge: [Individual] @stitch(source_field: "id", sink_field: "ID")
            }

            interface Individual {
              ID: String
              in_example_edge: [Human] @stitch(source_field: "ID", sink_field: "id")
            }

            type President implements Individual {
              ID: String
              year: Int
              in_example_edge: [Human] @stitch(source_field: "ID", sink_field: "id")
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_edge_inbound_side_interface(self):
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.basic_schema)),
                ('second', parse(ISS.interface_with_subclasses_schema)),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Individual',
                        field_name = 'ID',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Human',
                        field_name = 'id',
                    ),
                    out_edge_only=False,
                ),
            ]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Human: Human
              Individual: Individual
              President: President
            }

            type Human {
              id: String
              in_example_edge: [Individual] @stitch(source_field: "id", sink_field: "ID")
            }

            interface Individual {
              ID: String
              out_example_edge: [Human] @stitch(source_field: "ID", sink_field: "id")
            }

            type President implements Individual {
              ID: String
              year: Int
              out_example_edge: [Human] @stitch(source_field: "ID", sink_field: "id")
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))

    def test_edge_both_sides_interfaces(self):
        additional_interface_schema = dedent('''\
            schema {
              query: SchemaQuery
            }

            interface Person {
              identifier: String
              name: String
            }

            type Politician implements Person {
              identifier: String
              name: String
              party: String
            }

            type SchemaQuery {
              Person: Person
              Politician: Politician
            }
        ''')
        merged_schema = merge_schemas(
            OrderedDict([
                ('first', parse(ISS.interface_with_subclasses_schema)),
                ('second', parse(additional_interface_schema)),
            ]),
            [
                CrossSchemaEdgeDescriptor(
                    edge_name = 'example_edge',
                    outbound_side = FieldReference(
                        schema_id = 'first',
                        type_name = 'Individual',
                        field_name = 'ID',
                    ),
                    inbound_side = FieldReference(
                        schema_id = 'second',
                        type_name = 'Person',
                        field_name = 'identifier',
                    ),
                    out_edge_only=False,
                ),
            ]
        )
        merged_schema_string = dedent('''\
            schema {
              query: RootSchemaQuery
            }

            type RootSchemaQuery {
              Individual: Individual
              President: President
              Person: Person
              Politician: Politician
            }

            interface Individual {
              ID: String
              out_example_edge: [Person] @stitch(source_field: "ID", sink_field: "identifier")
            }

            type President implements Individual {
              ID: String
              year: Int
              out_example_edge: [Person] @stitch(source_field: "ID", sink_field: "identifier")
            }

            interface Person {
              identifier: String
              name: String
              in_example_edge: [Individual] @stitch(source_field: "identifier", sink_field: "ID")
            }

            type Politician implements Person {
              identifier: String
              name: String
              party: String
              in_example_edge: [Individual] @stitch(source_field: "identifier", sink_field: "ID")
            }
        ''')
        self.assertEqual(merged_schema_string, print_ast(merged_schema.schema_ast))


    # TODO:
    # The same thing as interfaces but with subclasses through unions and type_equivalence_hints
    # Adding edge to type that appears in type_equivalence_hints
    # combination of interface and unions
