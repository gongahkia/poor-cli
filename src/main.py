# ----- REQUIRED IMPORTS -----

import re
import argparse
import itertools
import random
from graphviz import Digraph

# ----- DATA MODELS -----
class Rule:
    def __init__(self, production, weight=1.0, optional=False):
        self.production = production
        self.weight = weight
        self.optional = optional

class Function:
    def __init__(self, name):
        self.name = name
        self.rules = []

    def add_rule(self, rule):
        self.rules.append(rule)

class Category:
    def __init__(self, name):
        self.name = name

class Grammar:
    def __init__(self):
        self.categories = []
        self.functions = {}

    def add_category(self, category):
        self.categories.append(category)

    def add_function(self, function):
        self.functions[function.name] = function

# ----- TOKENIZER CLASS -----

class Tokenizer:
    def __init__(self, code):
        self.code = code
        self.position = 0
        self.tokens = []

    def tokenize(self):
        while self.position < len(self.code):
            if self.code[self.position].isspace():
                self.position += 1
                continue
            elif self.code[self.position:self.position+6] == 'import':
                self.tokens.append(('import', 'import'))
                self.position += 6
            elif self.code[self.position:self.position+3] == 'cat':
                self.tokens.append(('cat', 'cat'))
                self.position += 3
            elif self.code[self.position:self.position+3] == 'fun':
                self.tokens.append(('fun', 'fun'))
                self.position += 3
            elif self.code[self.position:self.position+2] == '->':
                self.tokens.append(('arrow', '->'))
                self.position += 2
            elif self.code[self.position] == ':':
                self.tokens.append(('colon', ':'))
                self.position += 1
            elif self.code[self.position] == ';':
                self.tokens.append(('semicolon', ';'))
                self.position += 1
            elif self.code[self.position] == '(':
                self.position += 1
                weight = ''
                while self.position < len(self.code) and self.code[self.position] != ')':
                    weight += self.code[self.position]
                    self.position += 1
                self.position += 1
                self.tokens.append(('weight', float(weight)))
            elif self.code[self.position] == '?':
                self.tokens.append(('optional', '?'))
                self.position += 1
            elif self.code[self.position].isalpha():
                identifier = ''
                while self.position < len(self.code) and (self.code[self.position].isalnum() or self.code[self.position] == '_'):
                    identifier += self.code[self.position]
                    self.position += 1
                self.tokens.append(('identifier', identifier))
            else:
                self.position += 1
        return self.tokens

# ----- HELPER FUNCTIONS -----

def parse_gf(file_path, visited=None):
    if visited is None:
        visited = set()
    visited.add(file_path)

    with open(file_path, 'r') as file:
        content = file.read()
    
    tokenizer = Tokenizer(content)
    tokens = tokenizer.tokenize()
    
    grammar = Grammar()
    
    i = 0
    while i < len(tokens):
        if tokens[i][0] == 'import':
            i += 1
            imported_file = tokens[i][1] + '.gf'
            if imported_file not in visited:
                imported_grammar = parse_gf(imported_file, visited)
                for category in imported_grammar.categories:
                    grammar.add_category(category)
                for func_name, function in imported_grammar.functions.items():
                    if func_name not in grammar.functions:
                        grammar.add_function(function)
                    else:
                        for rule in function.rules:
                            grammar.functions[func_name].add_rule(rule)
            i += 1
        elif tokens[i][0] == 'cat':
            i += 1
            while i < len(tokens) and tokens[i][0] != 'fun':
                if tokens[i][0] == 'identifier':
                    grammar.add_category(Category(tokens[i][1]))
                i += 1
        elif tokens[i][0] == 'fun':
            i += 1
            while i < len(tokens) and tokens[i][0] != '----':
                if tokens[i][0] == 'identifier':
                    function = Function(tokens[i][1])
                    i += 1
                    while tokens[i][0] == 'colon':
                        i += 1
                        function.add_rule(Rule([tokens[i][1]]))
                        i+=1
                    
                    if tokens[i][0] == 'colon':
                        i += 1
                        rhs = []
                        weight = 1.0
                        optional = False
                        while i < len(tokens) and tokens[i][0] != 'semicolon':
                            if tokens[i][0] == 'identifier':
                                rhs.append(tokens[i][1])
                            elif tokens[i][0] == 'weight':
                                weight = tokens[i][1]
                            elif tokens[i][0] == 'optional':
                                optional = True
                            i += 1
                        
                        function.add_rule(Rule(rhs, weight, optional))
                    grammar.add_function(function)
                i += 1
        else:
            i += 1
            
    return grammar

def validate_grammar(grammar):
    defined_categories = {cat.name for cat in grammar.categories}
    used_categories = set(grammar.functions.keys())
    for func in grammar.functions.values():
        for rule in func.rules:
            for symbol in rule.production:
                used_categories.add(symbol)

    # Check for undefined categories
    for category in used_categories:
        if category not in defined_categories:
            print(f"Warning: Category '{category}' is used but not defined.")

    # Check for unreachable rules
    reachable_rules = set()
    q = ['Meal'] 
    while q:
        rule_name = q.pop(0)
        if rule_name not in reachable_rules:
            reachable_rules.add(rule_name)
            if rule_name in grammar.functions:
                for rule in grammar.functions[rule_name].rules:
                    for symbol in rule.production:
                        q.append(symbol)
    
    for func_name in grammar.functions:
        if func_name not in reachable_rules:
            print(f"Warning: Rule '{func_name}' is unreachable.")

    # Check for circular references
    for func_name in grammar.functions:
        path = [func_name]
        q = [iter(rule.production for rule in grammar.functions.get(func_name, Function(func_name)).rules)]
        while q:
            try:
                child = next(q[-1])
                if child in path:
                    print(f"Warning: Circular reference detected: {' -> '.join(path)} -> {child}")
                    continue
                if child in grammar.functions:
                    path.append(child)
                    q.append(iter(rule.production for rule in grammar.functions.get(child, Function(child)).rules))
            except StopIteration:
                path.pop()
                q.pop()

def generate_sentences(grammar, start_symbol='Meal', filter_pattern=None):

    def expand(symbol):
        if symbol not in grammar.functions:
            yield [symbol]
            return

        rules = grammar.functions[symbol].rules
        
        # Handle optional rules
        if len(rules) == 1 and rules[0].optional:
            if random.random() < 0.5:
                yield []
                return
        
        productions = [rule.production for rule in rules]
        weights = [rule.weight for rule in rules]
        chosen_production = random.choices(productions, weights=weights, k=1)[0]
        
        for production in chosen_production:
            if production.strip() == start_symbol:
                continue
            
            symbols = production.strip().split()
            if not symbols:
                yield []
                continue

            iterators = [expand(s) for s in symbols]
            for combination in itertools.product(*iterators):
                yield [item for sublist in combination for item in sublist]

    meal_function = next(func for func in grammar.functions.values() if func.rules[-1].production[-1].strip() == start_symbol)
    meal_components = [rule.production[0] for rule in meal_function.rules[:-1]]
    
    for combination in itertools.product(*[expand(comp.strip()) for comp in meal_components]):
        sentence = f"{meal_function.name} " + " ".join([item for sublist in combination for item in sublist])
        if filter_pattern:
            if re.search(filter_pattern, sentence):
                yield sentence
        else:
            yield sentence

def create_mermaid(sentences):
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
    parser_generate.add_argument('input', help='Path to the .gf grammar file')
    parser_generate.add_argument('-f', '--format', default='png',
                        choices=['png', 'pdf', 'svg', 'ascii'],
                        help='Output format (default: png)')
    parser_generate.add_argument('-l', '--limit', type=int, default=150,
                        help='Maximum number of sentences to generate (default: 150)')
    parser_generate.add_argument('--filter', help='Regex pattern to filter sentences')

    # Stats command
    parser_stats = subparsers.add_parser('stats', help='Calculate and display grammar statistics')
    parser_stats.add_argument('input', help='Path to the .gf grammar file')

    args = parser.parse_args()

    if args.command == 'generate':
        generate_and_visualize(args.input, args.format, args.limit, args.filter)
    elif args.command == 'stats':
        calculate_and_display_stats(args.input)

def generate_and_visualize(gf_file_path, output_format='png', limit=150, filter_pattern=None):
    grammar = parse_gf(gf_file_path)
    validate_grammar(grammar)
    
    sentences = []
    sentence_generator = generate_sentences(grammar, filter_pattern=filter_pattern)
    for i, sentence in enumerate(sentence_generator):
        if i >= limit:
            break
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

def calculate_and_display_stats(gf_file_path):
    grammar = parse_gf(gf_file_path)
    validate_grammar(grammar)

    # --- Metrics Calculation ---
    
    # 1. Total Permutations (using a helper function)
    memo = {}
    total_permutations = calculate_permutations(grammar, 'Meal', memo)

    # 2. Rule Coverage
    reachable_rules, all_rules = get_rule_coverage(grammar)
    unreachable_rules = all_rules - reachable_rules
    coverage_percentage = (len(reachable_rules) / len(all_rules)) * 100 if all_rules else 0

    # 3. Complexity Metrics
    total_rules = len(all_rules)
    avg_rules_per_cat = total_rules / len(grammar.categories) if grammar.categories else 0
    
    # --- Displaying Statistics ---
    
    print("--- Grammar Statistics ---")
    print(f"Total Possible Sentences (Permutations): {total_permutations}")
    print("\n--- Rule Coverage ---")
    print(f"Reachable Rules: {len(reachable_rules)}/{len(all_rules)} ({coverage_percentage:.2f}%)")
    if-unreachable_rules:
        print("Unreachable Rules:")
        for rule in sorted(list(unreachable_rules)):
            print(f"- {rule}")

    print("\n--- Complexity Metrics ---")
    print(f"Total Categories: {len(grammar.categories)}")
    print(f"Total Rules: {total_rules}")
    print(f"Average Rules per Category: {avg_rules_per_cat:.2f}")
    print("------------------------")

def calculate_permutations(grammar, symbol, memo):
    if symbol in memo:
        return memo[symbol]
    
    if symbol not in grammar.functions:
        return 1
    
    count = 0
    for rule in grammar.functions[symbol].rules:
        if rule.optional:
            # Optional rules can either be present or absent
            count += 1 
        
        production_count = 1
        for sub_symbol in rule.production:
            # To prevent infinite recursion on cycles
            if sub_symbol == symbol:
                continue
            production_count *= calculate_permutations(grammar, sub_symbol, memo)
        count += production_count

    memo[symbol] = count
    return count

def get_rule_coverage(grammar):
    all_rules = set(grammar.functions.keys())
    reachable_rules = set()
    q = ['Meal'] 
    
    visited = set()
    while q:
        rule_name = q.pop(0)
        if rule_name not in visited:
            visited.add(rule_name)
            reachable_rules.add(rule_name)
            if rule_name in grammar.functions:
                for rule in grammar.functions[rule_name].rules:
                    for symbol in rule.production:
                        q.append(symbol)
                        
    return reachable_rules, all_rules

# ----- EXECUTION CODE -----

if __name__ == "__main__":
    main()