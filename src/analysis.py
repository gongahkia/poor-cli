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


def merge_grammars(grammar1, grammar2, name=None):
    """
    Merge two abstract grammars into one.
    Categories and functions from both grammars are combined.
    Conflicting function names are prefixed with grammar name.
    """
    if not isinstance(grammar1, AbstractGrammar) or not isinstance(grammar2, AbstractGrammar):
        raise ValueError("Both grammars must be abstract grammars")

    merged_name = name or f"{grammar1.name}_{grammar2.name}_merged"
    merged = AbstractGrammar(merged_name)

    for cat_name, cat in grammar1.categories.items():
        merged.categories[cat_name] = cat
    for cat_name, cat in grammar2.categories.items():
        merged.categories[cat_name] = cat

    for func_name, func in grammar1.functions.items():
        merged.functions[func_name] = func
    for func_name, func in grammar2.functions.items():
        if func_name in merged.functions:
            new_name = f"{grammar2.name}_{func_name}"
            from .grammar import AbstractFunction
            merged.functions[new_name] = AbstractFunction(new_name, func.arg_types, func.return_type)
        else:
            merged.functions[func_name] = func

    for func_name, constraint in grammar1.constraints.items():
        merged.constraints[func_name] = constraint
    for func_name, constraint in grammar2.constraints.items():
        merged.constraints[func_name] = constraint

    return merged


def detect_ambiguity(abstract_grammar, concrete_grammar, sentence):
    """
    Detect if a sentence is ambiguous (can be parsed multiple ways).
    Returns a list of all possible ASTs that produce the sentence.
    """
    from .types import Category, AST
    from .generation import linearize

    words = sentence.lower().split()
    all_parses = []

    def find_all_parses(target_cat, remaining_words, depth=0):
        """Find all ASTs of target_cat that linearize to remaining_words."""
        if depth > 20:
            return []

        cat_name = target_cat.name if isinstance(target_cat, Category) else str(target_cat)

        # Find functions producing this category
        producing_funcs = [
            f for f in abstract_grammar.functions.values()
            if (f.return_type.name if isinstance(f.return_type, Category) else str(f.return_type)) == cat_name
        ]

        results = []
        for func in producing_funcs:
            # Terminal function (no args)
            if not func.arg_types:
                if func.name in concrete_grammar.linearization_rules:
                    rule = concrete_grammar.linearization_rules[func.name]
                    lin_words = []
                    for token in rule.body_tokens:
                        lin_words.extend(token.strip('"').lower().split())
                    if lin_words == remaining_words:
                        results.append((AST(func.name, []), []))
                continue

            # Non-terminal: try to match children
            child_parses = try_match_children(func, remaining_words, depth)
            for children, leftover in child_parses:
                results.append((AST(func.name, children), leftover))

        return results

    def try_match_children(func, words, depth):
        """Try to match function arguments against words."""
        if not func.arg_types:
            return [([], words)]

        if not words:
            return []

        # Get linearization rule
        if func.name not in concrete_grammar.linearization_rules:
            return []

        rule = concrete_grammar.linearization_rules[func.name]

        # Simple case: just children concatenated
        def recurse_children(arg_idx, remaining):
            if arg_idx >= len(func.arg_types):
                return [([], remaining)]

            results = []
            child_parses = find_all_parses(func.arg_types[arg_idx], remaining, depth + 1)

            for child_ast, leftover in child_parses:
                sub_results = recurse_children(arg_idx + 1, leftover)
                for sub_children, final_leftover in sub_results:
                    results.append(([child_ast] + sub_children, final_leftover))

            # Also try consuming more words for this child
            for split in range(1, len(remaining) + 1):
                child_parses = find_all_parses(func.arg_types[arg_idx], remaining[:split], depth + 1)
                for child_ast, leftover in child_parses:
                    if not leftover:  # Consumed exactly these words
                        sub_results = recurse_children(arg_idx + 1, remaining[split:])
                        for sub_children, final_leftover in sub_results:
                            results.append(([child_ast] + sub_children, final_leftover))

            return results

        return recurse_children(0, words)

    # Start parsing from Sentence category
    parses = find_all_parses(Category("Sentence"), words)

    # Filter to only complete parses (no leftover words)
    complete_parses = [ast for ast, leftover in parses if not leftover]

    # Deduplicate by AST string representation
    seen = set()
    unique_parses = []
    for ast in complete_parses:
        ast_str = str(ast)
        if ast_str not in seen:
            seen.add(ast_str)
            unique_parses.append(ast)

    return unique_parses


def build_dependency_graph(grammar):
    """
    Build a category dependency graph for visualization.
    Returns a dict mapping each category to its dependencies.
    """
    if not isinstance(grammar, AbstractGrammar):
        raise ValueError("Dependency graph only supported for abstract grammars")

    dependencies = {}

    for cat_name in grammar.categories:
        dependencies[cat_name] = set()

    for func in grammar.functions.values():
        ret_name = func.return_type.name if isinstance(func.return_type, Category) else str(func.return_type)

        for arg_type in func.arg_types:
            arg_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
            if ret_name in dependencies:
                dependencies[ret_name].add(arg_name)

    return {k: list(v) for k, v in dependencies.items()}


def visualize_dependencies(grammar, output_path=None, output_format='png'):
    """
    Create a visual dependency graph of categories.
    Returns the Graphviz Digraph object.
    """
    from graphviz import Digraph

    deps = build_dependency_graph(grammar)

    dot = Digraph(comment='Category Dependency Graph')
    dot.attr(rankdir='TB')
    dot.attr('node', shape='box', style='rounded,filled', fillcolor='#e3f2fd')

    # Add nodes
    for cat_name in deps:
        # Highlight Sentence as entry point
        if cat_name == 'Sentence':
            dot.node(cat_name, cat_name, fillcolor='#c8e6c9', penwidth='2')
        else:
            dot.node(cat_name, cat_name)

    # Add edges
    for cat_name, dep_cats in deps.items():
        for dep in dep_cats:
            if dep in deps:  # Only add edges to known categories
                dot.edge(cat_name, dep)

    if output_path:
        dot.render(output_path, format=output_format, cleanup=True)

    return dot


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
