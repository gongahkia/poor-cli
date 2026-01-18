# src/analysis.py

from .types import Category
from .grammar import AbstractGrammar


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


def minimize_grammar(grammar):
    """
    Minimizes an abstract grammar by removing unreachable rules.
    """
    if not isinstance(grammar, AbstractGrammar):
        return grammar  # Minimization only supported for abstract grammars for now.

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
    minimized_grammar.categories = grammar.categories  # For now, keep all categories

    for func_name in reachable_funcs:
        minimized_grammar.functions[func_name] = grammar.functions[func_name]

    return minimized_grammar


def extract_subgraph(grammar, start_category):
    """
    Extract a subgraph of the grammar starting from a specific category.
    Returns a new AbstractGrammar containing only reachable functions from that category.
    """
    if not isinstance(grammar, AbstractGrammar):
        raise ValueError("Subgraph extraction only supported for abstract grammars")

    subgraph = AbstractGrammar(f"{grammar.name}_{start_category}_subgraph")
    reachable_funcs = set()
    reachable_cats = set()

    def collect_reachable(cat_name, visited=None):
        if visited is None:
            visited = set()
        if cat_name in visited:
            return
        visited.add(cat_name)
        reachable_cats.add(cat_name)

        funcs = [f for f in grammar.functions.values()
                 if (f.return_type.name if isinstance(f.return_type, Category) else str(f.return_type)) == cat_name]

        for func in funcs:
            reachable_funcs.add(func.name)
            for arg_type in func.arg_types:
                arg_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
                collect_reachable(arg_name, visited)

    collect_reachable(start_category)

    for cat_name in reachable_cats:
        if cat_name in grammar.categories:
            subgraph.categories[cat_name] = grammar.categories[cat_name]

    for func_name in reachable_funcs:
        if func_name in grammar.functions:
            subgraph.functions[func_name] = grammar.functions[func_name]

    for func_name in reachable_funcs:
        if func_name in grammar.constraints:
            subgraph.constraints[func_name] = grammar.constraints[func_name]

    return subgraph


def calculate_complexity(grammar):
    """
    Calculate grammar complexity metrics.
    Returns dict with branching_factor, max_depth, estimated_sentences, reachability.
    """
    if not isinstance(grammar, AbstractGrammar):
        return {"error": "Complexity analysis only supported for abstract grammars"}

    # Find start category (Sentence by default)
    start_cat = "Sentence"

    # Calculate productions per category
    cat_productions = {}
    for func in grammar.functions.values():
        ret_type = func.return_type.name if isinstance(func.return_type, Category) else str(func.return_type)
        cat_productions[ret_type] = cat_productions.get(ret_type, 0) + 1

    # Branching factor
    if cat_productions:
        branching_factor = sum(cat_productions.values()) / len(cat_productions)
    else:
        branching_factor = 0

    # Calculate max depth via BFS
    def get_max_depth(cat_name, visited=None):
        if visited is None:
            visited = set()
        if cat_name in visited:
            return 0  # Cycle
        visited.add(cat_name)

        funcs = [f for f in grammar.functions.values()
                 if (f.return_type.name if isinstance(f.return_type, Category) else str(f.return_type)) == cat_name]

        if not funcs:
            return 1

        max_child_depth = 0
        for func in funcs:
            for arg_type in func.arg_types:
                arg_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
                child_depth = get_max_depth(arg_name, visited.copy())
                max_child_depth = max(max_child_depth, child_depth)

        return 1 + max_child_depth

    max_depth = get_max_depth(start_cat)

    # Estimate sentence count (product of productions per required category)
    def estimate_sentences(cat_name, visited=None):
        if visited is None:
            visited = set()
        if cat_name in visited:
            return 1

        visited.add(cat_name)
        funcs = [f for f in grammar.functions.values()
                 if (f.return_type.name if isinstance(f.return_type, Category) else str(f.return_type)) == cat_name]

        if not funcs:
            return 1

        total = 0
        for func in funcs:
            prod = 1
            for arg_type in func.arg_types:
                arg_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
                prod *= estimate_sentences(arg_name, visited.copy())
            total += prod
        return total

    estimated_sentences = estimate_sentences(start_cat)

    # Reachability
    minimized = minimize_grammar(grammar)
    reachability = len(minimized.functions) / len(grammar.functions) if grammar.functions else 1.0

    return {
        "branching_factor": round(branching_factor, 2),
        "max_depth": max_depth,
        "estimated_sentences": estimated_sentences,
        "reachability": round(reachability, 2),
        "total_functions": len(grammar.functions),
        "total_categories": len(grammar.categories)
    }
