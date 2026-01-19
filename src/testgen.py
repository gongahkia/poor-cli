# src/testgen.py

"""Test suite auto-generation from grammar."""

import json
from .types import Category
from .grammar import AbstractGrammar, ConcreteGrammar
from .generation import generate_exhaustive_asts, generate_random_ast, linearize


def generate_test_suite(abstract_grammar, concrete_grammar, max_depth=5, max_tests=100):
    """
    Generate a test suite from the grammar.
    Returns a dict with test cases and coverage information.
    """
    # Generate exhaustive ASTs up to depth
    asts = generate_exhaustive_asts(abstract_grammar, Category("Sentence"), max_depth)

    # Limit number of tests
    if len(asts) > max_tests:
        import random
        asts = random.sample(asts, max_tests)

    test_cases = []
    used_functions = set()
    used_categories = set()

    for i, ast in enumerate(asts):
        sentence = linearize(ast, concrete_grammar)

        # Collect coverage info
        funcs, cats = _collect_coverage(ast, abstract_grammar)
        used_functions.update(funcs)
        used_categories.update(cats)

        test_cases.append({
            "id": i + 1,
            "sentence": sentence,
            "ast": str(ast),
            "functions_used": list(funcs),
            "categories_used": list(cats)
        })

    # Calculate coverage
    total_functions = len(abstract_grammar.functions)
    total_categories = len(abstract_grammar.categories)

    coverage = {
        "functions_covered": len(used_functions),
        "functions_total": total_functions,
        "functions_percentage": round(100 * len(used_functions) / total_functions, 1) if total_functions else 0,
        "categories_covered": len(used_categories),
        "categories_total": total_categories,
        "categories_percentage": round(100 * len(used_categories) / total_categories, 1) if total_categories else 0,
        "uncovered_functions": list(set(abstract_grammar.functions.keys()) - used_functions),
        "uncovered_categories": list(set(abstract_grammar.categories.keys()) - used_categories)
    }

    return {
        "test_count": len(test_cases),
        "max_depth": max_depth,
        "coverage": coverage,
        "tests": test_cases
    }


def _collect_coverage(ast, grammar):
    """Recursively collect functions and categories used in an AST."""
    functions = set()
    categories = set()

    def collect(node):
        functions.add(node.func_name)

        if node.func_name in grammar.functions:
            func = grammar.functions[node.func_name]
            ret_name = func.return_type.name if isinstance(func.return_type, Category) else str(func.return_type)
            categories.add(ret_name)
            for arg_type in func.arg_types:
                arg_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
                categories.add(arg_name)

        for child in node.children:
            collect(child)

    collect(ast)
    return functions, categories


def generate_pytest_suite(abstract_grammar, concrete_grammar, max_depth=5, max_tests=50):
    """
    Generate a pytest test file from the grammar.
    Returns Python code as a string.
    """
    suite = generate_test_suite(abstract_grammar, concrete_grammar, max_depth, max_tests)

    lines = []
    lines.append('"""Auto-generated test suite from grammar."""')
    lines.append('')
    lines.append('import pytest')
    lines.append('')
    lines.append('')
    lines.append('# Test cases generated from grammar')
    lines.append(f'# Total tests: {suite["test_count"]}')
    lines.append(f'# Function coverage: {suite["coverage"]["functions_percentage"]}%')
    lines.append(f'# Category coverage: {suite["coverage"]["categories_percentage"]}%')
    lines.append('')
    lines.append('')
    lines.append('VALID_SENTENCES = [')

    for test in suite["tests"]:
        sentence = test["sentence"].replace('"', '\\"')
        lines.append(f'    "{sentence}",')

    lines.append(']')
    lines.append('')
    lines.append('')
    lines.append('@pytest.mark.parametrize("sentence", VALID_SENTENCES)')
    lines.append('def test_valid_sentence(sentence, grammar_parser):')
    lines.append('    """Test that sentence is valid according to grammar."""')
    lines.append('    result = grammar_parser.parse(sentence)')
    lines.append('    assert result is not None, f"Failed to parse: {sentence}"')
    lines.append('')
    lines.append('')
    lines.append('def test_coverage_report():')
    lines.append('    """Report coverage statistics."""')
    lines.append(f'    assert {suite["coverage"]["functions_covered"]} >= {suite["coverage"]["functions_total"] // 2}, \\')
    lines.append('        "Less than 50% function coverage"')
    lines.append('')

    return '\n'.join(lines)


def generate_json_test_suite(abstract_grammar, concrete_grammar, max_depth=5, max_tests=100):
    """Generate test suite as JSON."""
    suite = generate_test_suite(abstract_grammar, concrete_grammar, max_depth, max_tests)
    return json.dumps(suite, indent=2, ensure_ascii=False)
