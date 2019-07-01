class SchemaData(object):
    def __init__(self):
        self.query_type = None
        self.scalars = set()
        self.directives = set()
        self.has_extension = False


class SchemaError(Exception):
    pass
