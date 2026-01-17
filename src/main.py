# ----- REQUIRED IMPORTS -----

import re
import argparse
import itertools
import random
from graphviz import Digraph

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
    
    categories = []
    rules = {}
    
    i = 0
    while i < len(tokens):
        if tokens[i][0] == 'import':
            i += 1
            imported_file = tokens[i][1] + '.gf'
            if imported_file not in visited:
                imported_categories, imported_rules = parse_gf(imported_file, visited)
                categories.extend(imported_categories)
                for key, value in imported_rules.items():
                    if key not in rules:
                        rules[key] = []
                    rules[key].extend(value)
            i += 1
        elif tokens[i][0] == 'cat':
            i += 1
            while i < len(tokens) and tokens[i][0] != 'fun':
                if tokens[i][0] == 'identifier':
                    categories.append(tokens[i][1])
                i += 1
        elif tokens[i][0] == 'fun':
            i += 1
            while i < len(tokens) and tokens[i][0] != '----':
                if tokens[i][0] == 'identifier':
                    lhs = [tokens[i][1]]
                    i += 1
                    while tokens[i][0] == 'colon':
                        i += 1
                        lhs.append(tokens[i][1])
                        i+=1
                    
                    if tokens[i][0] == 'colon':
                        i += 1
                        rhs = []
                        weight = 1.0
                        while i < len(tokens) and tokens[i][0] != 'semicolon':
                            if tokens[i][0] == 'identifier':
                                rhs.append(tokens[i][1])
                            elif tokens[i][0] == 'weight':
                                weight = tokens[i][1]
                            i += 1
                        
                        for item in lhs:
                            if item not in rules:
                                rules[item] = []
                            rules[item].append((rhs, weight))
                i += 1
        else:
            i += 1
            
    return categories, rules

def validate_grammar(categories, rules):
    defined_categories = set(categories)
    used_categories = set(rules.keys())
    for rhs in rules.values():
        for symbol in rhs:
            used_categories.add(symbol)

    # Check for undefined categories
    for category in used_categories:
        if category not in defined_categories:
            print(f"Warning: Category '{category}' is used but not defined.")

    # Check for unreachable rules
    reachable_rules = set()
    q = ['Meal'] 
    while q:
        rule = q.pop(0)
        if rule not in reachable_rules:
            reachable_rules.add(rule)
            if rule in rules:
                for symbol in rules[rule]:
                    q.append(symbol)
    
    for rule in rules:
        if rule not in reachable_rules:
            print(f"Warning: Rule '{rule}' is unreachable.")

    # Check for circular references
    for category in rules:
        path = [category]
        q = [iter(rules.get(category, []))]
        while q:
            try:
                child = next(q[-1])
                if child in path:
                    print(f"Warning: Circular reference detected: {' -> '.join(path)} -> {child}")
                    continue
                if child in rules:
                    path.append(child)
                    q.append(iter(rules.get(child, [])))
            except StopIteration:
                path.pop()
                q.pop()

def generate_sentences(categories, rules, start_symbol='Meal'):

    def expand(symbol):
        if symbol not in rules:
            return [[symbol]]
        
        productions, weights = zip(*rules[symbol])
        chosen_production = random.choices(productions, weights=weights, k=1)[0]
        
        expansions = []
        for production in chosen_production:
            if production.strip() == start_symbol:
                continue  
            symbols = production.strip().split()
            symbol_expansions = [expand(s) for s in symbols]
            expansions.extend(itertools.product(*symbol_expansions))
        return expansions
    
    meal_function = next(func for func in rules if rules[func][-1][0][-1].strip() == start_symbol)
    meal_components = [item[0] for item in rules[meal_function][:-1]]
    
    sentences = []
    for combination in itertools.product(*[expand(comp.strip()) for comp in meal_components]):
        sentence = f"{meal_function} " + " ".join([item for sublist in combination for item in sublist])
        sentences.append(sentence)
    return sentences

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

def main(gf_file_path, output_format='png', limit=150):
    categories, rules = parse_gf(gf_file_path)
    validate_grammar(categories, rules)
    sentences = generate_sentences(categories, rules)
    sentences = sentences[:limit]
    print(f"Generated sentences (limited to {limit}):")
    for sentence in sentences:
        print(sentence)
    flowchart = create_mermaid(sentences)
    flowchart.render('sentence_permutations', format=output_format, cleanup=True)
    print(f"\nFlowchart saved as 'sentence_permutations.{output_format}'")

# ----- EXECUTION CODE -----

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Seuss - GF grammar file visualizer',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('input', help='Path to the .gf grammar file')
    parser.add_argument('-f', '--format', default='png',
                        choices=['png', 'pdf', 'svg'],
                        help='Output format (default: png)')
    parser.add_argument('-l', '--limit', type=int, default=150,
                        help='Maximum number of sentences to generate (default: 150)')
    args = parser.parse_args()
    main(args.input, args.format, args.limit)