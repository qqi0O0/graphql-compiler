from graphql_compiler import (
    ORIENTDB_SCHEMA_RECORDS_QUERY, get_graphql_schema_from_orientdb_records, graphql_to_match
)
from graphql_compiler.tests.conftest import init_integration_graph_client

# Initialize dummy OrientDB database and get client
client = init_integration_graph_client()

# Generate GraphQL schema from queried OrientDB schema records
schema_records = client.command(ORIENTDB_SCHEMA_RECORDS_QUERY)
schema, _ = get_graphql_schema_from_orientdb_records(schema_records)

# Write GraphQL query to get the names of all animals with a particular net worth
# Note that we prefix net_worth with '$' and surround it with quotes to indicate it's a parameter
graphql_query = '''
 {
     Animal {
         name @output(out_name: "animal_name")
         net_worth @filter(op_name: "=", value: ["$net_worth"])
     }
 }
 '''
parameters = {
    'net_worth': '100',
}

# Use autogenerated GraphQL schema to compile GraphQL query into Match, an OrientDB query language
compilation_result = graphql_to_match(schema, graphql_query, parameters)

# Run query in OrientDB
query = compilation_result.query
results = [row.oRecordData for row in client.command(query)]
