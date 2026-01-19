# ----- REQUIRED IMPORTS -----

import os
import cmd
import readline
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
    ConcreteGrammar,
    Category,
    generate_random_ast,
    generate_exhaustive_asts,
    validate_grammar,
    deduplicate_sentences,
    calculate_complexity,
    extract_subgraph,
    merge_grammars,
    detect_ambiguity
)

# ----- HELPER FUNCTIONS -----

def is_rtl_text(text):
    """Detect if text contains RTL characters (Arabic, Hebrew, etc.)."""
    import unicodedata
    for char in text:
        if unicodedata.bidirectional(char) in ('R', 'AL', 'AN'):
            return True
    return False

def create_graph(sentences):
    dot = Digraph(comment='Sentence Permutations')
    # Detect RTL and adjust layout
    has_rtl = any(is_rtl_text(s) for s in sentences)
    dot.attr(rankdir='RL' if has_rtl else 'LR')
    dot.attr('node', fontname='Noto Sans')  # Unicode-friendly font
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
    parser_generate.add_argument('--deduplicate', action='store_true', help='Remove duplicate sentences')

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

    # Validate command
    parser_validate = subparsers.add_parser('validate', help='Validate a grammar file')
    parser_validate.add_argument('input', help='Path to the .gf grammar file')

    # Minimize command
    parser_minimize = subparsers.add_parser('minimize', help='Minimize a grammar file')
    parser_minimize.add_argument('input', help='Path to the .gf grammar file')
    parser_minimize.add_argument('-o', '--output', help='Path to save the minimized grammar file')

    # REPL command
    parser_repl = subparsers.add_parser('repl', help='Start an interactive REPL session')
    parser_repl.add_argument('--abstract', required=True, help='Path to the abstract .gf grammar file')
    parser_repl.add_argument('--concrete', required=True, help='Path to the concrete .gf grammar file')

    # Coverage command
    parser_coverage = subparsers.add_parser('coverage', help='Analyze grammar coverage')
    parser_coverage.add_argument('--abstract', required=True, help='Path to the abstract .gf grammar file')
    parser_coverage.add_argument('--concrete', required=True, help='Path to the concrete .gf grammar file')
    parser_coverage.add_argument('sentences_file', help='Path to a file with test sentences')

    # Batch command
    parser_batch = subparsers.add_parser('batch', help='Batch process a directory of .gf files')
    parser_batch.add_argument('input_dir', help='Path to the input directory')
    parser_batch.add_argument('output_dir', help='Path to the output directory')
    parser_batch.add_argument('--abstract', required=True, help='Path to the abstract .gf grammar file')
    parser_batch.add_argument('-f', '--format', default='png',
                        choices=['png', 'pdf', 'svg', 'ascii'],
                        help='Output format (default: png)')
    parser_batch.add_argument('-l', '--limit', type=int, default=150,
                        help='Maximum number of sentences to generate (default: 150)')

    # Template command
    parser_template = subparsers.add_parser('template', help='Generate a new grammar template')
    parser_template.add_argument('name', help='Name of the new grammar')
    parser_template.add_argument('categories', nargs='+', help='List of categories for the new grammar')
    parser_template.add_argument('-o', '--output', help='Path to save the new grammar file')

    # Export command
    parser_export = subparsers.add_parser('export', help='Export grammar as JSON')
    parser_export.add_argument('input', help='Path to the .gf grammar file')
    parser_export.add_argument('-o', '--output', help='Path to save the JSON file')

    # Watch command
    parser_watch = subparsers.add_parser('watch', help='Watch grammar files and regenerate on change')
    parser_watch.add_argument('--abstract', required=True, help='Path to the abstract .gf grammar file')
    parser_watch.add_argument('--concrete', required=True, help='Path to the concrete .gf grammar file')
    parser_watch.add_argument('-f', '--format', default='png', choices=['png', 'pdf', 'svg', 'ascii'])
    parser_watch.add_argument('-l', '--limit', type=int, default=150)
    parser_watch.add_argument('--interval', type=float, default=1.0, help='Polling interval in seconds')

    # Complexity command
    parser_complexity = subparsers.add_parser('complexity', help='Analyze grammar complexity')
    parser_complexity.add_argument('input', help='Path to the abstract .gf grammar file')

    # Subgraph command
    parser_subgraph = subparsers.add_parser('subgraph', help='Extract and visualize a subgraph')
    parser_subgraph.add_argument('input', help='Path to the abstract .gf grammar file')
    parser_subgraph.add_argument('category', help='Starting category for subgraph')
    parser_subgraph.add_argument('-o', '--output', help='Path to save the subgraph grammar file')

    # Exhaust command
    parser_exhaust = subparsers.add_parser('exhaust', help='Generate all sentences up to a depth limit')
    parser_exhaust.add_argument('--abstract', required=True, help='Path to the abstract .gf grammar file')
    parser_exhaust.add_argument('--concrete', required=True, help='Path to the concrete .gf grammar file')
    parser_exhaust.add_argument('-d', '--depth', type=int, default=5, help='Maximum derivation depth (default: 5)')
    parser_exhaust.add_argument('--deduplicate', action='store_true', help='Remove duplicate sentences')

    # Merge command
    parser_merge = subparsers.add_parser('merge', help='Merge two abstract grammars')
    parser_merge.add_argument('grammar1', help='Path to first abstract .gf grammar file')
    parser_merge.add_argument('grammar2', help='Path to second abstract .gf grammar file')
    parser_merge.add_argument('-n', '--name', help='Name for merged grammar')
    parser_merge.add_argument('-o', '--output', help='Path to save merged grammar file')

    # Ambiguity command
    parser_ambiguity = subparsers.add_parser('ambiguity', help='Check if a sentence parses multiple ways')
    parser_ambiguity.add_argument('--abstract', required=True, help='Path to abstract .gf grammar file')
    parser_ambiguity.add_argument('--concrete', required=True, help='Path to concrete .gf grammar file')
    parser_ambiguity.add_argument('sentence', help='The sentence to check for ambiguity')

    args = parser.parse_args()

    if args.command == 'generate':
        generate_and_visualize(args.abstract, args.concrete, args.format, args.limit, args.filter, args.deduplicate)
    elif args.command == 'stats':
        calculate_and_display_stats(args.input)
    elif args.command == 'diff':
        diff_grammars(args.file1, args.file2)
    elif args.command == 'parse':
        reverse_parse_and_display(args.input, args.sentence)
    elif args.command == 'sample':
        sample_and_display(args.abstract, args.concrete, args.num_samples)
    elif args.command == 'validate':
        validate_grammar_and_display(args.input)
    elif args.command == 'minimize':
        minimize_grammar_and_display(args.input, args.output)
    elif args.command == 'repl':
        start_repl(args.abstract, args.concrete)
    elif args.command == 'coverage':
        analyze_coverage_and_display(args.abstract, args.concrete, args.sentences_file)
    elif args.command == 'batch':
        batch_visualize(args.input_dir, args.output_dir, args.abstract, args.format, args.limit)
    elif args.command == 'template':
        generate_template_and_display(args.name, args.categories, args.output)
    elif args.command == 'export':
        export_grammar_json(args.input, args.output)
    elif args.command == 'watch':
        watch_and_regenerate(args.abstract, args.concrete, args.format, args.limit, args.interval)
    elif args.command == 'complexity':
        display_complexity(args.input)
    elif args.command == 'subgraph':
        extract_and_display_subgraph(args.input, args.category, args.output)
    elif args.command == 'exhaust':
        exhaust_and_display(args.abstract, args.concrete, args.depth, args.deduplicate)
    elif args.command == 'merge':
        merge_and_display(args.grammar1, args.grammar2, args.name, args.output)
    elif args.command == 'ambiguity':
        check_ambiguity_and_display(args.abstract, args.concrete, args.sentence)


def check_ambiguity_and_display(abstract_path, concrete_path, sentence):
    abstract_grammar = parse_grammar(abstract_path)
    concrete_grammar = parse_grammar(concrete_path)

    if not isinstance(abstract_grammar, AbstractGrammar):
        print("Error: --abstract requires an abstract grammar file.")
        return
    if not isinstance(concrete_grammar, ConcreteGrammar):
        print("Error: --concrete requires a concrete grammar file.")
        return

    parses = detect_ambiguity(abstract_grammar, concrete_grammar, sentence)

    print(f"--- Ambiguity Analysis ---")
    print(f"Sentence: \"{sentence}\"")
    print(f"Parse count: {len(parses)}")

    if len(parses) == 0:
        print("Result: Sentence does not match the grammar.")
    elif len(parses) == 1:
        print("Result: Sentence is unambiguous.")
        print(f"AST: {parses[0]}")
    else:
        print("Result: Sentence is AMBIGUOUS!")
        for i, ast in enumerate(parses, 1):
            print(f"  Parse {i}: {ast}")
    print("--------------------------")


def merge_and_display(grammar1_path, grammar2_path, name, output_path):
    grammar1 = parse_grammar(grammar1_path)
    grammar2 = parse_grammar(grammar2_path)

    if not isinstance(grammar1, AbstractGrammar) or not isinstance(grammar2, AbstractGrammar):
        print("Error: Both inputs must be abstract grammar files.")
        return

    merged = merge_grammars(grammar1, grammar2, name)
    print(f"--- Merged Grammar ---")
    print(f"Name: {merged.name}")
    print(f"Categories: {len(merged.categories)}")
    print(f"Functions: {len(merged.functions)}")
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(merged.to_string())
        print(f"Saved to {output_path}")
    else:
        print(merged.to_string())
    print("----------------------")


def exhaust_and_display(abstract_path, concrete_path, max_depth, deduplicate):
    abstract_grammar = parse_grammar(abstract_path)
    concrete_grammar = parse_grammar(concrete_path)

    if not isinstance(abstract_grammar, AbstractGrammar):
        print("Error: --abstract requires an abstract grammar file.")
        return
    if not isinstance(concrete_grammar, ConcreteGrammar):
        print("Error: --concrete requires a concrete grammar file.")
        return

    asts = generate_exhaustive_asts(abstract_grammar, Category("Sentence"), max_depth)
    sentences = [linearize(ast, concrete_grammar) for ast in asts]

    if deduplicate:
        sentences = deduplicate_sentences(sentences)

    print(f"--- Exhaustive generation (depth={max_depth}) ---")
    print(f"Total sentences: {len(sentences)}")
    for i, sentence in enumerate(sentences, 1):
        print(f"({i}) {sentence}")
    print("------------------------------------")


def extract_and_display_subgraph(input_path, category, output_path):
    grammar = parse_grammar(input_path)
    subgraph = extract_subgraph(grammar, category)
    print(f"--- Subgraph from '{category}' ---")
    print(f"Categories: {len(subgraph.categories)}")
    print(f"Functions: {len(subgraph.functions)}")
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(subgraph.to_string())
        print(f"Saved to {output_path}")
    else:
        print(subgraph.to_string())

def display_complexity(input_path):
    grammar = parse_grammar(input_path)
    metrics = calculate_complexity(grammar)
    print(f"--- Complexity Analysis for {input_path} ---")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    print("--------------------------------------------")

def watch_and_regenerate(abstract_path, concrete_path, output_format, limit, interval):
    """Watch grammar files and regenerate visualization when they change."""
    import time
    from gf_lib import clear_grammar_cache

    def get_mtimes():
        return (os.path.getmtime(abstract_path), os.path.getmtime(concrete_path))

    last_mtimes = get_mtimes()
    print(f"Watching {abstract_path} and {concrete_path} (Ctrl+C to stop)")
    generate_and_visualize(abstract_path, concrete_path, output_format, limit)

    try:
        while True:
            time.sleep(interval)
            current_mtimes = get_mtimes()
            if current_mtimes != last_mtimes:
                print("\nChange detected, regenerating...")
                clear_grammar_cache()
                generate_and_visualize(abstract_path, concrete_path, output_format, limit)
                last_mtimes = current_mtimes
    except KeyboardInterrupt:
        print("\nStopped watching.")

def export_grammar_json(input_path, output_path):
    grammar = parse_grammar(input_path)
    json_output = grammar.to_json()
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_output)
        print(f"Grammar exported to {output_path}")
    else:
        print(json_output)

def generate_and_visualize(abstract_path, concrete_path, output_format='png', limit=150, filter_pattern=None, deduplicate=False):
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
        ast = generate_random_ast(abstract_grammar, Category("Sentence"))
        sentence = linearize(ast, concrete_grammar)
        if filter_pattern:
            if re.search(filter_pattern, sentence):
                sentences.append(sentence)
        else:
            sentences.append(sentence)

    if deduplicate:
        sentences = deduplicate_sentences(sentences)

    print(f"Generated {len(sentences)} sentences:")
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

import cmd
import readline

class Repl(cmd.Cmd):
    """Interactive REPL for exploring grammars."""
    
    prompt = '> '
    
    def __init__(self, abstract_grammar, concrete_grammar):
        super().__init__()
        self.abstract_grammar = abstract_grammar
        self.concrete_grammar = concrete_grammar
        self.last_ast = None

    def do_ls(self, arg):
        """List all functions in the abstract grammar."""
        for func_name in self.abstract_grammar.functions:
            print(func_name)

    def do_info(self, arg):
        """Show information about a function."""
        if arg in self.abstract_grammar.functions:
            func = self.abstract_grammar.functions[arg]
            print(f"Function: {func.name}")
            print(f"Type: {' -> '.join(map(str, func.arg_types))} -> {func.return_type}")
        else:
            print(f"Unknown function: {arg}")

    def complete_info(self, text, line, begidx, endidx):
        return [f for f in self.abstract_grammar.functions if f.startswith(text)]

    def do_generate(self, arg):
        """Generate a random AST from a category."""
        cat = Category(arg) if arg else Category("Sentence")
        self.last_ast = generate_random_ast(self.abstract_grammar, cat)
        print(self.last_ast)

    def complete_generate(self, text, line, begidx, endidx):
        return [c for c in self.abstract_grammar.categories if c.startswith(text)]
        
    def do_linearize(self, arg):
        """Linearize the last generated AST."""
        if self.last_ast:
            sentence = linearize(self.last_ast, self.concrete_grammar)
            print(sentence)
        else:
            print("No AST generated yet. Use 'generate' first.")

    def do_exit(self, arg):
        """Exit the REPL."""
        return True

import os

def generate_template_and_display(name, categories, output_path):
    
    template = f"abstract {name} =\n"
    template += "cat\n"
    for cat in categories:
        template += f"  {cat} ;\n"
    
    template += "\nfun\n"
    
    # Add some example functions
    for i, cat in enumerate(categories):
        template += f"  Make{cat} : {cat} -> {cat} ;\n"
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(template)
        print(f"Grammar template saved to {output_path}")
    else:
        print("--- Grammar Template ---")
        print(template)
        print("------------------------")


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
        ast = generate_random_ast(abstract_grammar, Category("Sentence"))
        sentence = linearize(ast, concrete_grammar)
        print(f"({i+1}) {sentence}")
    print("------------------------------------")

# ----- EXECUTION CODE -----

if __name__ == "__main__":
    main()