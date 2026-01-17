# ----- REQUIRED IMPORTS -----

import re
import argparse
import itertools
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

def parse_gf(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    
    tokenizer = Tokenizer(content)
    tokens = tokenizer.tokenize()
    
    categories = []
    rules = {}
    
    i = 0
    while i < len(tokens):
        if tokens[i][0] == 'cat':
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
                        while i < len(tokens) and tokens[i][0] != 'semicolon':
                            if tokens[i][0] == 'identifier':
                                rhs.append(tokens[i][1])
                            i += 1
                        
                        for item in lhs:
                            rules[item] = rhs
                i += 1
        else:
            i += 1
            
    return categories, rules

def generate_sentences(categories, rules, start_symbol='Meal'):

    def expand(symbol):
        if symbol not in rules:
            return [[symbol]]
        expansions = []
        for production in rules[symbol]:
            if production.strip() == start_symbol:
                continue  
            symbols = production.strip().split()
            symbol_expansions = [expand(s) for s in symbols]
            expansions.extend(itertools.product(*symbol_expansions))
        return expansions
    meal_function = next(func for func in rules if rules[func][-1].strip() == start_symbol)
    meal_components = rules[meal_function][:-1]  
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