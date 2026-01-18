# src/gf_lib.py

import re
import json
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
    in_constraints = False

    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith('--'):
            continue

        parts = line.split()
        if parts[0] == 'cat':
            in_constraints = False
            for cat_name in parts[1:]:
                if cat_name != ';':
                    grammar.categories[cat_name] = {}
        elif parts[0] == 'fun':
            in_constraints = False
            name = parts[1]
            signature = " ".join(parts[3:])

            arg_types_str, return_type_str = signature.rsplit('->', 1)

            arg_types = _parse_type_list(arg_types_str.strip())
            return_type = _parse_type(return_type_str.strip())

            grammar.functions[name] = AbstractFunction(name, arg_types, return_type)
        elif parts[0] == 'constraints':
            in_constraints = True
        elif in_constraints and 'requires' in line:
            # Parse: FuncName requires Category=Value ;
            match = re.match(r'(\w+)\s+requires\s+(\w+)\s*=\s*(\w+)', line)
            if match:
                func_name, cat_name, value = match.groups()
                if func_name not in grammar.constraints:
                    grammar.constraints[func_name] = Constraint(func_name, {})
                if cat_name not in grammar.constraints[func_name].requires:
                    grammar.constraints[func_name].requires[cat_name] = []
                grammar.constraints[func_name].requires[cat_name].append(value)

    return grammar

class ConcreteRule:
    """Represents a concrete linearization rule."""
    def __init__(self, abstract_func_name, body_tokens):
        self.abstract_func_name = abstract_func_name
        self.body_tokens = body_tokens

    def to_dict(self):
        return {"abstract_func_name": self.abstract_func_name, "body_tokens": self.body_tokens}

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
            grammar.lincat_rules[cat_name] = " ".join(parts[3:])
        elif parts[0] == 'lin':
            func_name = parts[1]
            body_str = " ".join(parts[3:])
            # Tokenize the body by the '++' operator
            body_tokens = [t.strip() for t in body_str.split('++')]
            grammar.linearization_rules[func_name] = ConcreteRule(func_name, body_tokens)
            
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
        
        result = []
        child_index = 0
        for token in rule.body_tokens:
            if token in [f.name for f in ast.children]:
                # This is a simplification. It assumes token directly maps to a child's func_name
                # A proper implementation would need to handle variables like 'x', 'y'
                result.append(linearize(ast.children[child_index], concrete_grammar))
                child_index += 1
            else:
                # The token is a literal string
                result.append(token.strip('"'))
        
        return " ".join(result)
        
    # If there is no rule, it might be a literal from the abstract syntax.
    return ast.func_name

def string_to_ast(sentence, concrete_grammar, abstract_grammar):
    """
    Parses a string into an AST and returns the AST and a set of used rule names.
    This is a placeholder for a real parsing algorithm.
    """
    
    words = sentence.split()
    
    # This is a highly simplified and incomplete stub.
    # A real implementation would need a proper parsing algorithm.
    
    def find_func_for_word(word):
        for func, rule in concrete_grammar.linearization_rules.items():
            if word in " ".join(rule.body_tokens): # Simplification
                return func
        return None

    func_name = find_func_for_word(words[0])
    if not func_name:
        return None, set()
        
    children = [AST(w) for w in words[1:]]
    
    # For now, we'll just claim the top-level function was used.
    used_rules = {func_name}
    
    return AST(func_name, children), used_rules

def minimize_grammar(grammar):

    """

    Minimizes an abstract grammar by removing unreachable rules.

    """

    if not isinstance(grammar, AbstractGrammar):

        return grammar # Minimization only supported for abstract grammars for now.



    reachable_funcs = set()

    

    # Start traversal from functions that produce 'Sentence'

    q = [f.name for f in grammar.functions.values() if f.return_type.name == 'Sentence']

    

    while q:

        func_name = q.pop(0)

        if func_name in reachable_funcs:

            continue

            

        reachable_funcs.add(func_name)

        

        func = grammar.functions[func_name]

        for arg_type in func.arg_types:

            

            # Find functions that produce this argument type

            producing_funcs = [f.name for f in grammar.functions.values() if f.return_type.name == arg_type.name]

            q.extend(producing_funcs)



    # Create a new minimized grammar

    minimized_grammar = AbstractGrammar(grammar.name)

    minimized_grammar.categories = grammar.categories # For now, keep all categories



    for func_name in reachable_funcs:

        minimized_grammar.functions[func_name] = grammar.functions[func_name]

        

    return minimized_grammar


def generate_random_ast(grammar, category, context=None, max_depth=20):
    """
    Generate a random AST for the given category.
    Respects constraints based on previously selected categories.
    """
    if context is None:
        context = {}

    if max_depth <= 0:
        return None

    cat_name = category.name if isinstance(category, Category) else str(category)

    # Find all functions that produce this category
    producing_funcs = [
        f for f in grammar.functions.values()
        if (f.return_type.name if isinstance(f.return_type, Category) else str(f.return_type)) == cat_name
    ]

    # Filter by constraints
    valid_funcs = []
    for func in producing_funcs:
        if func.name in grammar.constraints:
            if grammar.constraints[func.name].is_satisfied(context):
                valid_funcs.append(func)
        else:
            valid_funcs.append(func)

    if not valid_funcs:
        return None

    # Pick a random function
    func = random.choice(valid_funcs)

    # Update context with this selection
    new_context = context.copy()
    new_context[cat_name] = func.name

    # Recursively generate children
    children = []
    for arg_type in func.arg_types:
        child = generate_random_ast(grammar, arg_type, new_context, max_depth - 1)
        if child is None:
            return None
        children.append(child)

    return AST(func.name, children)


def deduplicate_sentences(sentences, normalize=True):
    """
    Remove duplicate sentences from a list.
    If normalize=True, also removes semantically equivalent sentences
    by normalizing whitespace and case.
    """
    seen = set()
    unique = []
    for sentence in sentences:
        key = sentence
        if normalize:
            key = ' '.join(sentence.lower().split())
        if key not in seen:
            seen.add(key)
            unique.append(sentence)
    return unique
