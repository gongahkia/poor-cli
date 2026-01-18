# ----- REQUIRED IMPORTS -----

import re
import argparse
import itertools
import random
from graphviz import Digraph

from gf_lib import (
    parse_grammar,
    linearize,
    string_to_ast,
    AST,
    AbstractGrammar,
    ConcreteGrammar
)

# ----- HELPER FUNCTIONS -----

def create_graph(sentences):
    dot = Digraph(comment='Sentence Permutations')
    dot.attr(rankdir='LR')
    for i, sentence in enumerate(sentences):
        words = sentence.split()
        for j, word in enumerate(words):
            node_id = f"s{i}_{j}"
            dot.node(node_id, word)
            if j > 0:
                prev_node_id = f"s{i}_{j-1}"
                dot.edge(prev_node_id, node_id)
    return dot

def main():
    parser = argparse.ArgumentParser(
        description='Seuss - GF grammar file visualizer',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Generate command
    parser_generate = subparsers.add_parser('generate', help='Generate sentences and visualize')
    parser_generate.add_argument('--abstract', required=True, help='Path to the abstract .gf grammar file')
    parser_generate.add_argument('--concrete', required=True, help='Path to the concrete .gf grammar file')
    parser_generate.add_argument('-f', '--format', default='png',
                        choices=['png', 'pdf', 'svg', 'ascii'],
                        help='Output format (default: png)')
    parser_generate.add_argument('-l', '--limit', type=int, default=150,
                        help='Maximum number of sentences to generate (default: 150)')
    parser_generate.add_argument('--filter', help='Regex pattern to filter sentences')

    # Stats command
    parser_stats = subparsers.add_parser('stats', help='Calculate and display grammar statistics')
    parser_stats.add_argument('input', help='Path to the .gf grammar file')

    # Diff command
    parser_diff = subparsers.add_parser('diff', help='Compare two .gf files and show structural differences')
    parser_diff.add_argument('file1', help='Path to the first .gf grammar file')
    parser_diff.add_argument('file2', help='Path to the second .gf grammar file')

    # Parse command
    parser_parse = subparsers.add_parser('parse', help='Check if a sentence matches the grammar')
    parser_parse.add_argument('input', help='Path to the .gf grammar file')
    parser_parse.add_argument('sentence', help='The sentence to parse')

    # Sample command
    parser_sample = subparsers.add_parser('sample', help='Generate random valid sentences')
    parser_sample.add_argument('--abstract', required=True, help='Path to the abstract .gf grammar file')
    parser_sample.add_argument('--concrete', required=True, help='Path to the concrete .gf grammar file')
    parser_sample.add_argument('-n', '--num_samples', type=int, default=1,
                        help='Number of random sentences to generate (default: 1)')

    args = parser.parse_args()

    if args.command == 'generate':
        generate_and_visualize(args.abstract, args.concrete, args.format, args.limit, args.filter)
    elif args.command == 'stats':
        calculate_and_display_stats(args.input)
    elif args.command == 'diff':
        diff_grammars(args.file1, args.file2)
    elif args.command == 'parse':
        reverse_parse_and_display(args.input, args.sentence)
    elif args.command == 'sample':
        sample_and_display(args.abstract, args.concrete, args.num_samples)

def generate_and_visualize(abstract_path, concrete_path, output_format='png', limit=150, filter_pattern=None):
    abstract_grammar = parse_grammar(abstract_path)
    concrete_grammar = parse_grammar(concrete_path)

    if not isinstance(abstract_grammar, AbstractGrammar):
        print("Error: --abstract requires an abstract grammar file.")
        return
    if not isinstance(concrete_grammar, ConcreteGrammar):
        print("Error: --concrete requires a concrete grammar file.")
        return
        
    sentences = []
    for _ in range(limit):
        ast = generate_random_ast(abstract_grammar)
        sentence = linearize(ast, concrete_grammar)
        if filter_pattern:
            if re.search(filter_pattern, sentence):
                sentences.append(sentence)
        else:
            sentences.append(sentence)

    print(f"Generated sentences (limited to {limit}):")
    for sentence in sentences:
        print(sentence)

    graph = create_graph(sentences)

    if output_format == 'ascii':
        from graph_easy import EasyGraph
        easy_graph = EasyGraph()
        for edge in graph.body:
            if '->' in edge:
                parts = edge.split('->')
                node1 = parts[0].strip().split(' ')[0]
                node2 = parts[1].strip().split(' ')[0]
                easy_graph.add_edge(node1, node2)
        print(easy_graph.to_ascii())
    else:
        graph.render('sentence_permutations', format=output_format, cleanup=True)
        print(f"\nFlowchart saved as 'sentence_permutations.{output_format}'")

def calculate_and_display_stats(gf_file_path):
    grammar = parse_grammar(gf_file_path)
    
    print(f"--- Statistics for {gf_file_path} ---")

    if isinstance(grammar, AbstractGrammar):
        print("Type: Abstract Grammar")
        print(f"Name: {grammar.name}")
        print(f"Categories: {len(grammar.categories)}")
        print(f"Functions: {len(grammar.functions)}")
    elif isinstance(grammar, ConcreteGrammar):
        print("Type: Concrete Grammar")
        print(f"Name: {grammar.name}")
        print(f"Abstract Grammar: {grammar.abstract_name}")
        print(f"Linearization Rules: {len(grammar.linearization_rules)}")
        print(f"Lincat Rules: {len(grammar.lincat_rules)}")
    else:
        print("Unknown grammar type.")
        
    print("------------------------------------")

def diff_grammars(file1_path, file2_path):
    grammar1 = parse_grammar(file1_path)
    grammar2 = parse_grammar(file2_path)

    print(f"--- Diffing {file1_path} and {file2_path} ---")

    if type(grammar1) != type(grammar2):
        print("Error: Cannot diff grammars of different types.")
        return

    if isinstance(grammar1, AbstractGrammar):
        # Compare Abstract Grammars
        cats1 = set(grammar1.categories.keys())
        cats2 = set(grammar2.categories.keys())
        
        print(f"Added Categories: {cats2 - cats1}")
        print(f"Removed Categories: {cats1 - cats2}")

        funcs1 = set(grammar1.functions.keys())
        funcs2 = set(grammar2.functions.keys())

        print(f"Added Functions: {funcs2 - funcs1}")
        print(f"Removed Functions: {funcs1 - funcs2}")

    elif isinstance(grammar1, ConcreteGrammar):
        # Compare Concrete Grammars
        rules1 = set(grammar1.linearization_rules.keys())
        rules2 = set(grammar2.linearization_rules.keys())

        print(f"Added Linearization Rules: {rules2 - rules1}")
        print(f"Removed Linearization Rules: {rules1 - rules2}")

    print("------------------------------------")

def reverse_parse_and_display(gf_file_path, sentence):
    concrete_grammar = parse_grammar(gf_file_path)
    if not isinstance(concrete_grammar, ConcreteGrammar):
        print("Error: Parsing requires a concrete grammar.")
        return
        
    abstract_grammar = parse_grammar(f"grammers/singlish/{concrete_grammar.abstract_name}.gf")
    
    ast = string_to_ast(sentence, concrete_grammar, abstract_grammar)
    
    if ast:
        print("Sentence is valid. AST:")
        print(ast)
    else:
        print("Sentence is not valid according to the grammar.")

def sample_and_display(abstract_path, concrete_path, num_samples):
    abstract_grammar = parse_grammar(abstract_path)
    concrete_grammar = parse_grammar(concrete_path)

    if not isinstance(abstract_grammar, AbstractGrammar):
        print("Error: --abstract requires an abstract grammar file.")
        return
    if not isinstance(concrete_grammar, ConcreteGrammar):
        print("Error: --concrete requires a concrete grammar file.")
        return

    print(f"--- Generating {num_samples} random sentences ---")
    for i in range(num_samples):
        ast = generate_random_ast(abstract_grammar)
        sentence = linearize(ast, concrete_grammar)
        print(f"({i+1}) {sentence}")
    print("------------------------------------")

# ----- EXECUTION CODE -----

if __name__ == "__main__":
    main()
