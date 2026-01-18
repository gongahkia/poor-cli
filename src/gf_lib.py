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
)

from .analysis import (
    validate_grammar,
    minimize_grammar,
    extract_subgraph,
    calculate_complexity,
    merge_grammars,
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
    # Analysis
    'validate_grammar',
    'minimize_grammar',
    'extract_subgraph',
    'calculate_complexity',
    'merge_grammars',
    # Generation
    'generate_random_ast',
    'generate_exhaustive_asts',
    'linearize',
    'string_to_ast',
    'deduplicate_sentences',
    # Utils
    'normalize_unicode',
    'clear_grammar_cache',
]
