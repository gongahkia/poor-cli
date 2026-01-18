# src/gf_lib.py

class AST:
    """Represents a node in the Abstract Syntax Tree."""
    def __init__(self, func_name, children=None):
        self.func_name = func_name
        self.children = children if children else []

    def __repr__(self):
        if not self.children:
            return self.func_name
        return f"{self.func_name}({', '.join(map(str, self.children))})"

class AbstractGrammar:
    """Represents an abstract grammar."""
    def __init__(self, name):
        self.name = name
        self.categories = {}
        self.functions = {}

class ConcreteGrammar:
    """Represents a concrete grammar."""
    def __init__(self, name, abstract_name):
        self.name = name
        self.abstract_name = abstract_name
        self.linearization_rules = {}
        self.lincat_rules = {}

class AbstractFunction:
    """Represents an abstract function signature."""
    def __init__(self, name, arg_types, return_type):
        self.name = name
        self.arg_types = arg_types
        self.return_type = return_type

def parse_grammar(file_path):
    """Parses a .gf file and returns either an AbstractGrammar or a ConcreteGrammar."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    lines = content.splitlines()
    first_line = lines[0].strip()

    if first_line.startswith('abstract'):
        return _parse_abstract_grammar(lines)
    elif first_line.startswith('concrete'):
        return _parse_concrete_grammar(lines)
    else:
        raise ValueError("Invalid grammar file: must start with 'abstract' or 'concrete'")

def _parse_abstract_grammar(lines):
    grammar_name = lines[0].strip().split()[1]
    grammar = AbstractGrammar(grammar_name)

    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith('--'):
            continue
        
        parts = line.split()
        if parts[0] == 'cat':
            for cat_name in parts[1:]:
                if cat_name != ';':
                    grammar.categories[cat_name] = {}
        elif parts[0] == 'fun':
            name = parts[1]
            # simplified parsing of type signature
            arg_types = [p for p in parts[3:-2] if p != '->']
            return_type = parts[-2]
            grammar.functions[name] = AbstractFunction(name, arg_types, return_type)
            
    return grammar

def validate_grammar(grammar):
    """
    Performs validation checks on a grammar, starting with cycle detection for abstract grammars.
    Returns a list of validation warnings.
    """
    warnings = []
    if isinstance(grammar, AbstractGrammar):
        for func_name in grammar.functions:
            path = [func_name]
            
            # This is a simplified cycle detection and may not cover all complex cases.
            q = [iter(grammar.functions[func_name].arg_types)]
            
            while q:
                try:
                    child_cat = next(q[-1])
                    
                    # Find functions that produce this category
                    producing_funcs = [f.name for f in grammar.functions.values() if f.return_type == child_cat]
                    
                    for p_func in producing_funcs:
                        if p_func in path:
                            warnings.append(f"Cycle detected: {' -> '.join(path)} -> {p_func}")
                            continue
                        
                        path.append(p_func)
                        q.append(iter(grammar.functions[p_func].arg_types))

                except StopIteration:
                    path.pop()
                    q.pop()
                    
    return warnings
