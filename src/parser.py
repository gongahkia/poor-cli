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
