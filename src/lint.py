# src/lint.py

"""Grammar linting with common issue detection."""

from .types import Category
from .grammar import AbstractGrammar, ConcreteGrammar


def lint_grammar(grammar):
    """
    Perform linting checks on a grammar.
    Returns a list of LintIssue objects.
    """
    issues = []

    if isinstance(grammar, AbstractGrammar):
        issues.extend(_lint_abstract_grammar(grammar))
    elif isinstance(grammar, ConcreteGrammar):
        issues.extend(_lint_concrete_grammar(grammar))

    return issues


def _lint_abstract_grammar(grammar):
    """Lint an abstract grammar."""
    issues = []

    # Check for unused categories
    used_cats = set()
    for func in grammar.functions.values():
        for arg_type in func.arg_types:
            cat_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
            used_cats.add(cat_name)
        ret_name = func.return_type.name if isinstance(func.return_type, Category) else str(func.return_type)
        used_cats.add(ret_name)

    for cat_name in grammar.categories:
        if cat_name not in used_cats:
            issues.append(LintIssue(
                "warning",
                "unused_category",
                f"Category '{cat_name}' is defined but never used in any function"
            ))

    # Check for unreachable functions (not reachable from Sentence)
    reachable = _find_reachable_functions(grammar, "Sentence")
    for func_name in grammar.functions:
        if func_name not in reachable:
            issues.append(LintIssue(
                "warning",
                "unreachable_function",
                f"Function '{func_name}' is not reachable from 'Sentence'"
            ))

    # Check for undefined categories (referenced but not in cat)
    for func in grammar.functions.values():
        for arg_type in func.arg_types:
            cat_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
            if cat_name not in grammar.categories:
                issues.append(LintIssue(
                    "error",
                    "undefined_category",
                    f"Function '{func.name}' references undefined category '{cat_name}'"
                ))
        ret_name = func.return_type.name if isinstance(func.return_type, Category) else str(func.return_type)
        if ret_name not in grammar.categories:
            issues.append(LintIssue(
                "error",
                "undefined_category",
                f"Function '{func.name}' returns undefined category '{ret_name}'"
            ))

    # Check for categories with no producing functions
    for cat_name in grammar.categories:
        producing = [f for f in grammar.functions.values()
                     if (f.return_type.name if isinstance(f.return_type, Category) else str(f.return_type)) == cat_name]
        if not producing:
            issues.append(LintIssue(
                "warning",
                "no_producer",
                f"Category '{cat_name}' has no function that produces it"
            ))

    # Check for potential infinite recursion (simple cycles)
    for func in grammar.functions.values():
        ret_name = func.return_type.name if isinstance(func.return_type, Category) else str(func.return_type)
        for arg_type in func.arg_types:
            arg_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
            if arg_name == ret_name:
                issues.append(LintIssue(
                    "warning",
                    "self_recursive",
                    f"Function '{func.name}' is directly recursive (arg type equals return type)"
                ))

    # Check for duplicate function names (shouldn't happen but check anyway)
    seen_funcs = {}
    for func_name in grammar.functions:
        if func_name in seen_funcs:
            issues.append(LintIssue(
                "error",
                "duplicate_function",
                f"Duplicate function name: '{func_name}'"
            ))
        seen_funcs[func_name] = True

    # Check for empty grammar
    if not grammar.functions:
        issues.append(LintIssue(
            "error",
            "empty_grammar",
            "Grammar has no functions defined"
        ))

    if not grammar.categories:
        issues.append(LintIssue(
            "error",
            "no_categories",
            "Grammar has no categories defined"
        ))

    # Check for missing Sentence category
    if "Sentence" not in grammar.categories:
        issues.append(LintIssue(
            "warning",
            "no_sentence_category",
            "Grammar has no 'Sentence' category (standard entry point)"
        ))

    return issues


def _lint_concrete_grammar(grammar):
    """Lint a concrete grammar."""
    issues = []

    # Check for empty linearization rules
    for func_name, rule in grammar.linearization_rules.items():
        if not rule.body_tokens:
            issues.append(LintIssue(
                "warning",
                "empty_linearization",
                f"Function '{func_name}' has empty linearization rule"
            ))

    # Check for missing lincat rules
    if not grammar.lincat_rules:
        issues.append(LintIssue(
            "warning",
            "no_lincat",
            "Concrete grammar has no lincat rules"
        ))

    return issues


def _find_reachable_functions(grammar, start_category):
    """Find all functions reachable from a starting category."""
    reachable = set()
    visited_cats = set()

    def visit(cat_name):
        if cat_name in visited_cats:
            return
        visited_cats.add(cat_name)

        # Find functions that produce this category
        producing = [f for f in grammar.functions.values()
                     if (f.return_type.name if isinstance(f.return_type, Category) else str(f.return_type)) == cat_name]

        for func in producing:
            reachable.add(func.name)
            for arg_type in func.arg_types:
                arg_name = arg_type.name if isinstance(arg_type, Category) else str(arg_type)
                visit(arg_name)

    visit(start_category)
    return reachable


class LintIssue:
    """Represents a linting issue."""

    def __init__(self, severity, code, message):
        self.severity = severity  # "error", "warning", "info"
        self.code = code
        self.message = message

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.code}: {self.message}"

    def to_dict(self):
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message
        }
