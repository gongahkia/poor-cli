# src/grammar.py

import json


class AbstractFunction:
    """Represents an abstract function signature."""
    def __init__(self, name, arg_types, return_type):
        self.name = name
        self.arg_types = arg_types
        self.return_type = return_type

    def to_dict(self):
        return {
            "name": self.name,
            "arg_types": [t.to_dict() for t in self.arg_types],
            "return_type": self.return_type.to_dict()
        }


class AbstractGrammar:
    """Represents an abstract grammar."""
    def __init__(self, name):
        self.name = name
        self.categories = {}
        self.functions = {}
        self.constraints = {}  # func_name -> Constraint

    def to_string(self):
        s = f"abstract {self.name}\n\n"
        s += "cat\n"
        for cat_name in self.categories:
            s += f"  {cat_name} ;\n"
        s += "\nfun\n"
        for func in self.functions.values():
            args = " -> ".join(map(str, func.arg_types))
            s += f"  {func.name} : {args} -> {func.return_type} ;\n"
        return s

    def to_dict(self):
        return {
            "grammar_type": "abstract",
            "name": self.name,
            "categories": list(self.categories.keys()),
            "functions": {k: v.to_dict() for k, v in self.functions.items()},
            "constraints": {k: v.to_dict() for k, v in self.constraints.items()}
        }

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class ConcreteRule:
    """Represents a concrete linearization rule."""
    def __init__(self, abstract_func_name, body_tokens):
        self.abstract_func_name = abstract_func_name
        self.body_tokens = body_tokens

    def to_dict(self):
        return {"abstract_func_name": self.abstract_func_name, "body_tokens": self.body_tokens}


class ConcreteGrammar:
    """Represents a concrete grammar."""
    def __init__(self, name, abstract_name):
        self.name = name
        self.abstract_name = abstract_name
        self.linearization_rules = {}
        self.lincat_rules = {}

    def to_dict(self):
        return {
            "grammar_type": "concrete",
            "name": self.name,
            "abstract_name": self.abstract_name,
            "linearization_rules": {k: v.to_dict() for k, v in self.linearization_rules.items()},
            "lincat_rules": self.lincat_rules
        }

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
