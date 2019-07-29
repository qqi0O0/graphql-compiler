from graphql.language.visitor import visit, Visitor
from graphql.language import ast as ast_types


class QueryASTNode(object):
    """A tree node wrapping around a query AST.

    Used to represent a part of a split query. The tree as whole represents dependencies among
    the split query pieces. If node A is a child of node B, then the execution of the query
    piece in node A is dependent on some outputs of the query piece in node B.
    """
    def __init__(self, query_ast, input_parameter_name=None, parent_node=None):
        """Create a SplitQueryASTNode.

        Args:
            query_ast: Document, representing a piece of the split query
            input_parameter_name: str, parameter name used to stitch together this query piece
                                  and its parent. Used as the out_name of the stitched
                                  field in both the current query piece and the parent query
                                  piece's output, and as the input parameter name for the
                                  @filter directive in the current query piece
            parent_node: QueryASTNode, if the current node has a parent
        """
        self.query_ast = query_ast
        self.input_parameter_name = input_parameter_name
        self.parent_node = parent_node
        self.child_nodes = []  # List[QueryASTNode], defined upon backwards traversal of tree

    # Possibly define operations for dfs and bfs


def split_query(query_ast, pas):
    pass
