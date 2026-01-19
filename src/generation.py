# src/generation.py

import random

from .types import Category, AST
from .utils import normalize_unicode


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
            if word in " ".join(rule.body_tokens):  # Simplification
                return func
        return None

    func_name = find_func_for_word(words[0])
    if not func_name:
        return None, set()

    children = [AST(w) for w in words[1:]]

    # For now, we'll just claim the top-level function was used.
    used_rules = {func_name}

    return AST(func_name, children), used_rules


def generate_exhaustive_asts(grammar, category, max_depth=5, context=None):
    """
    Generate ALL possible ASTs for the given category up to a specified depth.
    Returns a list of AST objects representing all valid derivations.
    """
    if context is None:
        context = {}

    if max_depth <= 0:
        return []

    cat_name = category.name if isinstance(category, Category) else str(category)

    producing_funcs = [
        f for f in grammar.functions.values()
        if (f.return_type.name if isinstance(f.return_type, Category) else str(f.return_type)) == cat_name
    ]

    valid_funcs = []
    for func in producing_funcs:
        if func.name in grammar.constraints:
            if grammar.constraints[func.name].is_satisfied(context):
                valid_funcs.append(func)
        else:
            valid_funcs.append(func)

    if not valid_funcs:
        return []

    all_asts = []
    for func in valid_funcs:
        new_context = context.copy()
        new_context[cat_name] = func.name

        if not func.arg_types:
            all_asts.append(AST(func.name, []))
            continue

        children_options = []
        for arg_type in func.arg_types:
            child_asts = generate_exhaustive_asts(grammar, arg_type, max_depth - 1, new_context)
            if not child_asts:
                break
            children_options.append(child_asts)

        if len(children_options) == len(func.arg_types):
            import itertools
            for combo in itertools.product(*children_options):
                all_asts.append(AST(func.name, list(combo)))

    return all_asts


def parallel_linearize(ast, concrete_grammars):
    """
    Linearize an AST using multiple concrete grammars in parallel.
    Returns a dict mapping grammar name to linearized sentence.
    """
    results = {}
    for grammar in concrete_grammars:
        results[grammar.name] = linearize(ast, grammar)
    return results


def generate_parallel_sentences(abstract_grammar, concrete_grammars, num_sentences=10):
    """
    Generate sentences in parallel across multiple concrete grammars.
    Returns a list of dicts with AST and linearizations for each grammar.
    """
    results = []

    for _ in range(num_sentences):
        ast = generate_random_ast(abstract_grammar, Category("Sentence"))
        if ast is None:
            continue

        entry = {
            "ast": str(ast),
            "linearizations": {}
        }

        for grammar in concrete_grammars:
            entry["linearizations"][grammar.name] = linearize(ast, grammar)

        results.append(entry)

    return results


def format_parallel_output(results, format_type='table'):
    """
    Format parallel generation results.
    format_type: 'table', 'markdown', or 'json'
    """
    if not results:
        return ""

    grammar_names = list(results[0]["linearizations"].keys())

    if format_type == 'json':
        import json
        return json.dumps(results, indent=2, ensure_ascii=False)

    elif format_type == 'markdown':
        lines = []
        # Header
        header = "| # | " + " | ".join(grammar_names) + " |"
        separator = "|" + "|".join(["---"] * (len(grammar_names) + 1)) + "|"
        lines.append(header)
        lines.append(separator)

        for i, entry in enumerate(results, 1):
            row = f"| {i} | "
            row += " | ".join(entry["linearizations"].get(name, "") for name in grammar_names)
            row += " |"
            lines.append(row)

        return "\n".join(lines)

    else:  # table
        lines = []
        # Calculate column widths
        widths = [5] + [max(len(name), max(len(e["linearizations"].get(name, "")) for e in results))
                       for name in grammar_names]

        # Header
        header = f"{'#':^5} | "
        header += " | ".join(f"{name:^{widths[i+1]}}" for i, name in enumerate(grammar_names))
        lines.append(header)
        lines.append("-" * len(header))

        for i, entry in enumerate(results, 1):
            row = f"{i:^5} | "
            row += " | ".join(f"{entry['linearizations'].get(name, ''):^{widths[j+1]}}"
                             for j, name in enumerate(grammar_names))
            lines.append(row)

        return "\n".join(lines)


def deduplicate_sentences(sentences, normalize=True):
    """
    Remove duplicate sentences from a list.
    If normalize=True, also removes semantically equivalent sentences
    by normalizing whitespace, case, and Unicode.
    """
    seen = set()
    unique = []
    for sentence in sentences:
        key = sentence
        if normalize:
            key = normalize_unicode(' '.join(sentence.lower().split()))
        if key not in seen:
            seen.add(key)
            unique.append(sentence)
    return unique
