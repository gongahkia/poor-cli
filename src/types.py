# src/types.py

class Type:
    """Base class for grammar types."""
    pass


class Category(Type):
    """Represents a simple category."""
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name

    def to_dict(self):
        return {"type": "Category", "name": self.name}


class ParameterizedCategory(Type):
    """Represents a parameterized category, e.g., List[Protein]."""
    def __init__(self, base, params):
        self.base = base
        self.params = params

    def __repr__(self):
        return f"{self.base}[{', '.join(map(str, self.params))}]"

    def to_dict(self):
        return {"type": "ParameterizedCategory", "base": self.base, "params": [p.to_dict() for p in self.params]}


class AST:
    """Represents a node in the Abstract Syntax Tree."""
    def __init__(self, func_name, children=None):
        self.func_name = func_name
        self.children = children if children else []

    def __repr__(self):
        if not self.children:
            return self.func_name
        return f"{self.func_name}({', '.join(map(str, self.children))})"

    def to_dict(self):
        return {"func_name": self.func_name, "children": [c.to_dict() for c in self.children]}


class Constraint:
    """Represents a conditional constraint on function application."""
    def __init__(self, func_name, requires):
        self.func_name = func_name
        self.requires = requires  # dict of {category_name: [allowed_values]}

    def is_satisfied(self, context):
        """Check if constraint is satisfied given current context."""
        for cat, allowed in self.requires.items():
            if cat in context and context[cat] not in allowed:
                return False
        return True

    def to_dict(self):
        return {"func_name": self.func_name, "requires": self.requires}
