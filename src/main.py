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
    parser_sample.add_argument('input', help='Path to the .gf grammar file')
    parser_sample.add_argument('-n', '--num_samples', type=int, default=1,
                        help='Number of random sentences to generate (default: 1)')

    args = parser.parse_args()

    if args.command == 'generate':
        generate_and_visualize(args.input, args.format, args.limit, args.filter)
    elif args.command == 'stats':
        calculate_and_display_stats(args.input)
    elif args.command == 'diff':
        diff_grammars(args.file1, args.file2)
    elif args.command == 'parse':
        reverse_parse_and_display(args.input, args.sentence)
    elif args.command == 'sample':
        sample_and_display(args.input, args.num_samples)

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

def diff_grammars(file1_path, file2_path):
    grammar1 = parse_gf(file1_path)
    grammar2 = parse_gf(file2_path)

    print(f"--- Diffing {file1_path} and {file2_path} ---")

    # Compare Categories
    cats1 = {cat.name for cat in grammar1.categories}
    cats2 = {cat.name for cat in grammar2.categories}
    
    added_cats = cats2 - cats1
    removed_cats = cats1 - cats2

    if added_cats:
        print("\nAdded Categories:")
        for cat in added_cats:
            print(f"+ {cat}")
    
    if removed_cats:
        print("\nRemoved Categories:")
        for cat in removed_cats:
            print(f"- {cat}")

    # Compare Functions
    funcs1 = set(grammar1.functions.keys())
    funcs2 = set(grammar2.functions.keys())

    added_funcs = funcs2 - funcs1
    removed_funcs = funcs1 - funcs2
    common_funcs = funcs1.intersection(funcs2)

    if added_funcs:
        print("\nAdded Functions:")
        for func in added_funcs:
            print(f"+ {func}")

    if removed_funcs:
        print("\nRemoved Functions:")
        for func in removed_funcs:
            print(f"- {func}")
            
    modified_funcs = []
    for func_name in common_funcs:
        func1 = grammar1.functions[func_name]
        func2 = grammar2.functions[func_name]
        if not compare_rules(func1.rules, func2.rules):
            modified_funcs.append(func_name)

    if modified_funcs:
        print("\nModified Functions:")
        for func in modified_funcs:
            print(f"~ {func}")
            
    print("\n------------------------")

def sample_and_display(gf_file_path, num_samples):
    grammar = parse_gf(gf_file_path)
    validate_grammar(grammar)
    
    print(f"--- Generating {num_samples} random sentences ---")
    for i in range(num_samples):
        sentence = generate_random_sentence(grammar)
        print(f"({i+1}) {sentence}")
    print("------------------------------------")

def generate_random_sentence(grammar, start_symbol='Meal'):

    def expand_random(symbol):
        if symbol not in grammar.functions:
            return [symbol]

        rules = grammar.functions[symbol].rules
        
        if len(rules) == 1 and rules[0].optional and random.random() < 0.5:
            return []
        
        productions = [rule.production for rule in rules]
        weights = [rule.weight for rule in rules]
        chosen_production = random.choices(productions, weights=weights, k=1)[0]
        
        result = []
        for sub_symbol in chosen_production:
            result.extend(expand_random(sub_symbol))
        return result

    meal_function = next(func for func in grammar.functions.values() if func.rules[-1].production[-1].strip() == start_symbol)
    
    # This assumes the meal composition is defined in the rules of the 'Meal' function
    # and we randomly pick one of these rules to start.
    initial_rule = random.choice(meal_function.rules)
    
    sentence_parts = [meal_function.name]
    for symbol in initial_rule.production:
        sentence_parts.extend(expand_random(symbol.strip()))
        
    return " ".join(sentence_parts)

def reverse_parse(grammar, words, start_symbol='Meal'):
    
    memo = {}

    def parse_recursive(symbol, index):
        if (symbol, index) in memo:
            return memo[(symbol, index)]

        if index >= len(words):
            return None # Reached end of input

        if symbol not in grammar.functions:
            if words[index] == symbol:
                return [(symbol, words[index])], index + 1
            else:
                return None

        for rule in grammar.functions[symbol].rules:
            path = []
            current_index = index
            match = True
            
            for sub_symbol in rule.production:
                result = parse_recursive(sub_symbol, current_index)
                if result:
                    sub_path, next_index = result
                    path.extend(sub_path)
                    current_index = next_index
                else:
                    match = False
                    break
            
            if match:
                memo[(symbol, index)] = ([(symbol, rule.production)] + path, current_index)
                return ([(symbol, rule.production)] + path, current_index)

        memo[(symbol, index)] = None
        return None

    result = parse_recursive(start_symbol, 0)
    if result and result[1] == len(words):
        return result[0]
    else:
        return None

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