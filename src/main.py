# ----- REQUIRED IMPORTS -----

import re
import argparse
import itertools
from graphviz import Digraph

# ----- HELPER FUNCTIONS -----

def parse_gf(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    categories = re.findall(r'cat\s+([\s\S]*?)fun', content)[0].strip().split(';')
    categories = [cat.strip() for cat in categories if cat.strip()]
    functions = re.findall(r'fun\s+([\s\S]*?)----', content)[0].strip().split(';')
    functions = [func.strip() for func in functions if func.strip()]
    rules = {}
    for func in functions:
        if ':' in func:
            lhs, rhs = func.split(':')
            lhs = lhs.strip().split(',')
            rhs = rhs.strip().split('->')
            for item in lhs:
                rules[item.strip()] = rhs
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