# src/gf_lib.py

import re
import random

class Type:
    """Base class for grammar types."""
    pass

class Category(Type):
    """Represents a simple category."""
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name

class ParameterizedCategory(Type):
    """Represents a parameterized category, e.g., List[Protein]."""
    def __init__(self, base, params):
        self.base = base
        self.params = params
    def __repr__(self):
        return f"{self.base}[{', '.join(map(str, self.params))}]"

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

class ConcreteRule:
    """Represents a concrete linearization rule."""
    def __init__(self, abstract_func_name, body):
        self.abstract_func_name = abstract_func_name
        self.body = body


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
            signature = " ".join(parts[3:])
            
            arg_types_str, return_type_str = signature.rsplit('->', 1)
            
            arg_types = _parse_type_list(arg_types_str.strip())
            return_type = _parse_type(return_type_str.strip())

            grammar.functions[name] = AbstractFunction(name, arg_types, return_type)
            
    return grammar

def _parse_concrete_grammar(lines):
    header_parts = lines[0].strip().split()
    grammar_name = header_parts[1]
    abstract_name = header_parts[3]
    grammar = ConcreteGrammar(grammar_name, abstract_name)

    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith('--'):
            continue
            
        parts = line.split()
        if parts[0] == 'lincat':
            cat_name = parts[1]
            # Further processing of lincat would be needed for complex cases
            grammar.lincat_rules[cat_name] = " ".join(parts[3:])
        elif parts[0] == 'lin':
            func_name = parts[1]
            # Simplified parsing of the rule body
            body = " ".join(parts[3:])
            grammar.linearization_rules[func_name] = ConcreteRule(func_name, body)
            
    return grammar


def _parse_type_list(s):
    # This is a simplified parser for a list of types
    return [_parse_type(t.strip()) for t in s.split('->')]

def _parse_type(s):
    # This function parses a type string, including parameterized types
    match = re.match(r'(\w+)(\[.+\])?', s)
    if not match:
        raise ValueError(f"Invalid type string: {s}")
        
    base_name = match.group(1)
    params_str = match.group(2)
    
    if params_str:
        # Remove brackets and split params
        params = [p.strip() for p in params_str[1:-1].split(',')]
        # Recursively parse param types
        param_types = [_parse_type(p) for p in params]
        return ParameterizedCategory(base_name, param_types)
    else:
        return Category(base_name)


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
            
            def check_cycles(current_type):
                
                # Find functions that can produce the given category
                producing_funcs = [f.name for f in grammar.functions.values() if f.return_type.name == current_type.name]
                
                for p_func in producing_funcs:
                    if p_func in path:
                        warnings.append(f"Cycle detected: {' -> '.join(path)} -> {p_func}")
                        continue
                    
                    path.append(p_func)
                    for arg_type in grammar.functions[p_func].arg_types:
                        check_cycles(arg_type)
                    path.pop()

            for arg_type in grammar.functions[func_name].arg_types:
                check_cycles(arg_type)
                    
    return warnings

def linearize(ast, concrete_grammar):
    """Recursively linearizes an AST into a string."""
    
    if ast.func_name in concrete_grammar.linearization_rules:
        rule = concrete_grammar.linearization_rules[ast.func_name]
        
        # This is a very simplified placeholder for variable substitution.
        # A real implementation would need to parse the rule body and substitute children's
        # linearizations correctly.
        
        # For now, let's assume rules are simple concatenations of children's linearizations
        
        linearized_children = [linearize(child, concrete_grammar) for child in ast.children]
        
        # Placeholder logic: just join the linearized children
        # This will not work for most GF grammars but is a start.
        return " ".join(linearized_children)
        
    # If there is no rule, it might be a literal.
    return ast.func_name

def string_to_ast(sentence, concrete_grammar, abstract_grammar):
    """Parses a string into an AST. This is a placeholder for a real parsing algorithm."""
    
    words = sentence.split()
    
    # This is a highly simplified and incomplete stub. A real implementation
    # would need a proper parsing algorithm (e.g., Earley, CYK) to handle ambiguity,
    # and to correctly match linearization rules.
    
    def find_func_for_word(word):
        # Reverse lookup: find which function could produce this word.
        # This is non-trivial. For now, assume a direct match.
        for func, rule in concrete_grammar.linearization_rules.items():
            # This is a massive oversimplification.
            if word in rule.body:
                return func
        return None

    # A very basic attempt to build an AST
    # This will only work for the simplest of grammars.
    
    func_name = find_func_for_word(words[0])
    if not func_name:
        return None
        
    # This part is also a stub. A real parser would recursively build the tree.
    children = [AST(w) for w in words[1:]]
    
    return AST(func_name, children)

def generate_random_ast(grammar, category):
    """Generates a random AST from an abstract grammar."""
    
    # Find functions that can produce the given category
    
    if isinstance(category, ParameterizedCategory):
        # This is a simplification. A real implementation would need a robust way
        # to handle generic types. For now, we just look for functions that return
        # the base of the parameterized type.
        
        candidate_funcs = [f for f in grammar.functions.values() if f.return_type.name == category.base]
    else:
        candidate_funcs = [f for f in grammar.functions.values() if f.return_type.name == category.name]

    if not candidate_funcs:
        return AST(category.name) 

    chosen_func = random.choice(candidate_funcs)
    
    children = [generate_random_ast(grammar, arg_type) for arg_type in chosen_func.arg_types]
    
    return AST(chosen_func.name, children)