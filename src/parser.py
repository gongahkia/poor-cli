# src/parser.py

import re
import os
from pathlib import Path

from .types import Category, ParameterizedCategory, Constraint
from .grammar import AbstractGrammar, ConcreteGrammar, AbstractFunction, ConcreteRule
from .utils import normalize_unicode, _is_cache_valid, _get_file_hash, set_grammar_cache, get_grammar_cache


def parse_grammar(file_path, use_cache=True):
    """
    Parses a .gf file and returns either an AbstractGrammar or a ConcreteGrammar.
    Uses incremental parsing with caching for performance.
    """
    file_path = str(Path(file_path).resolve())

    # Check cache
    if use_cache and _is_cache_valid(file_path):
        return get_grammar_cache()[file_path][2]

    with open(file_path, 'r', encoding='utf-8') as f:
        content = normalize_unicode(f.read())

    lines = content.splitlines()
    first_line = lines[0].strip()

    if first_line.startswith('abstract'):
        grammar = _parse_abstract_grammar(lines)
    elif first_line.startswith('concrete'):
        grammar = _parse_concrete_grammar(lines)
    else:
        raise ValueError("Invalid grammar file: must start with 'abstract' or 'concrete'")

    # Cache the result
    if use_cache:
        mtime = os.path.getmtime(file_path)
        file_hash = _get_file_hash(content)
        set_grammar_cache(file_path, mtime, file_hash, grammar)

    return grammar


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


def parse_ebnf(content, grammar_name="Imported"):
    """
    Parse EBNF/BNF notation and convert to AbstractGrammar.

    Supports formats:
    - BNF: <rule> ::= <term1> | <term2>
    - EBNF: rule = term1 | term2 ;
    """
    grammar = AbstractGrammar(grammar_name)

    lines = content.strip().split('\n')
    current_rule = ""

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//') or line.startswith('--'):
            continue

        current_rule += " " + line

        # Check if rule is complete (ends with ; for EBNF or no continuation)
        if ';' in current_rule or '::=' in current_rule:
            _parse_ebnf_rule(current_rule.strip(), grammar)
            current_rule = ""

    # Handle any remaining rule
    if current_rule.strip():
        _parse_ebnf_rule(current_rule.strip(), grammar)

    return grammar


def _parse_ebnf_rule(rule_text, grammar):
    """Parse a single EBNF/BNF rule and add to grammar."""
    from .grammar import AbstractFunction

    rule_text = rule_text.rstrip(';').strip()

    # Detect format: BNF uses ::=, EBNF uses =
    if '::=' in rule_text:
        parts = rule_text.split('::=', 1)
        separator = '::='
    elif '=' in rule_text:
        parts = rule_text.split('=', 1)
        separator = '='
    else:
        return

    if len(parts) != 2:
        return

    lhs = parts[0].strip()
    rhs = parts[1].strip()

    # Clean up BNF angle brackets
    lhs = lhs.strip('<>').strip()

    # Add category
    grammar.categories[lhs] = {}

    # Parse alternatives
    alternatives = [alt.strip() for alt in rhs.split('|')]

    for i, alt in enumerate(alternatives):
        if not alt:
            continue

        # Parse the alternative to extract referenced categories
        tokens = _tokenize_ebnf_alt(alt)
        arg_types = []

        for token in tokens:
            # Check if it's a non-terminal (reference to another rule)
            clean_token = token.strip('<>').strip('"\'')
            if token.startswith('<') and token.endswith('>'):
                # BNF non-terminal
                arg_types.append(Category(clean_token))
                if clean_token not in grammar.categories:
                    grammar.categories[clean_token] = {}
            elif token.startswith('"') or token.startswith("'"):
                # Terminal - skip for now (linearization would handle this)
                pass
            elif token.isalnum() or '_' in token:
                # Could be a non-terminal reference
                if token[0].isupper():
                    arg_types.append(Category(token))
                    if token not in grammar.categories:
                        grammar.categories[token] = {}

        # Create function name
        func_name = f"{lhs}_{i+1}" if len(alternatives) > 1 else f"Make{lhs}"

        # Add function
        grammar.functions[func_name] = AbstractFunction(
            func_name,
            arg_types,
            Category(lhs)
        )


def _tokenize_ebnf_alt(alt):
    """Tokenize an EBNF/BNF alternative."""
    tokens = []
    current = ""
    in_string = False
    string_char = None

    i = 0
    while i < len(alt):
        char = alt[i]

        if in_string:
            current += char
            if char == string_char:
                tokens.append(current)
                current = ""
                in_string = False
        elif char in '"\'':
            if current:
                tokens.append(current)
                current = ""
            current = char
            in_string = True
            string_char = char
        elif char == '<':
            if current:
                tokens.append(current)
                current = ""
            # Find closing >
            end = alt.find('>', i)
            if end != -1:
                tokens.append(alt[i:end+1])
                i = end
            else:
                current = char
        elif char.isspace():
            if current:
                tokens.append(current)
                current = ""
        else:
            current += char

        i += 1

    if current:
        tokens.append(current)

    return tokens


def parse_ebnf_file(file_path, grammar_name=None):
    """Parse an EBNF/BNF file and return an AbstractGrammar."""
    from pathlib import Path

    file_path = str(Path(file_path).resolve())

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if grammar_name is None:
        grammar_name = Path(file_path).stem

    return parse_ebnf(content, grammar_name)


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
