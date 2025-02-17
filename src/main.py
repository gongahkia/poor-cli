# ----- REQUIRED IMPORTS -----

import re
import itertools
from graphviz import Digraph

# ----- HELPER FUNCTIONS -----

def parse_gf(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    rules = {}
    for line in content.split('\n'):
        if ':' in line:
            lhs, rhs = line.split(':')
            lhs = lhs.strip()
            rhs = [r.strip() for r in rhs.split('|')]
            rules[lhs] = rhs
    return rules

def generate_sentences(rules, start_symbol='S'):

    def expand(symbol):
        if symbol not in rules:
            return [symbol]
        expansions = []
        for production in rules[symbol]:
            symbols = production.split()
            symbol_expansions = [expand(s) for s in symbols]
            expansions.extend(itertools.product(*symbol_expansions))
        return expansions
    return [' '.join(sentence) for sentence in expand(start_symbol)]

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

def main(gf_file_path):
    rules = parse_gf(gf_file_path)
    sentences = generate_sentences(rules)
    print("Generated sentences:")
    for sentence in sentences:
        print(sentence)
    flowchart = create_mermaid(sentences)
    flowchart.render('sentence_permutations', format='png', cleanup=True)
    print("\nMermaid flowchart has been saved as 'sentence_permutations.png'")

# ----- EXECUTION CODE -----

if __name__ == "__main__":
    gf_file_path = input("Enter the path to your GF file: ")
    main(gf_file_path)