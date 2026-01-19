# src/gf_lib.py
# Re-exports all public API from submodules for backwards compatibility

from .types import (
    Type,
    Category,
    ParameterizedCategory,
    AST,
    Constraint,
)

from .grammar import (
    AbstractGrammar,
    ConcreteGrammar,
    AbstractFunction,
    ConcreteRule,
)

from .parser import (
    parse_grammar,
    parse_ebnf,
    parse_ebnf_file,
)

from .analysis import (
    validate_grammar,
    minimize_grammar,
    extract_subgraph,
    calculate_complexity,
    merge_grammars,
    detect_ambiguity,
    build_dependency_graph,
    visualize_dependencies,
)

from .generation import (
    generate_random_ast,
    generate_exhaustive_asts,
    linearize,
    string_to_ast,
    deduplicate_sentences,
)

from .utils import (
    normalize_unicode,
    clear_grammar_cache,
)

from .export import (
    export_to_latex,
    export_to_html,
)

from .lint import (
    lint_grammar,
    LintIssue,
)

from .testgen import (
    generate_test_suite,
    generate_pytest_suite,
    generate_json_test_suite,
)

__all__ = [
    # Types
    'Type',
    'Category',
    'ParameterizedCategory',
    'AST',
    'Constraint',
    # Grammar
    'AbstractGrammar',
    'ConcreteGrammar',
    'AbstractFunction',
    'ConcreteRule',
    # Parser
    'parse_grammar',
    'parse_ebnf',
    'parse_ebnf_file',
    # Analysis
    'validate_grammar',
    'minimize_grammar',
    'extract_subgraph',
    'calculate_complexity',
    'merge_grammars',
    'detect_ambiguity',
    'build_dependency_graph',
    'visualize_dependencies',
    # Generation
    'generate_random_ast',
    'generate_exhaustive_asts',
    'linearize',
    'string_to_ast',
    'deduplicate_sentences',
    # Utils
    'normalize_unicode',
    'clear_grammar_cache',
    # Export
    'export_to_latex',
    'export_to_html',
    # Lint
    'lint_grammar',
    'LintIssue',
    # Test generation
    'generate_test_suite',
    'generate_pytest_suite',
    'generate_json_test_suite',
]
