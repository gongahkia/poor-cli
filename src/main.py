import re
import itertools
from graphviz import Digraph

def parse_gf_file(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    
    # Extract categories and functions
    categories = re.findall(r'cat\s+([\s\S]*?)fun', content)[0].strip().split(';')
    categories = [cat.strip() for cat in categories if cat.strip()]
    
    functions = re.findall(r'fun\s+([\s\S]*?)----', content)[0].strip().split(';')
    functions = [func.strip() for func in functions if func.strip()]
    
    # Parse functions into a dictionary
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
                continue  # Skip recursive definitions
            symbols = production.strip().split()
            symbol_expansions = [expand(s) for s in symbols]
            expansions.extend(itertools.product(*symbol_expansions))
        
        return expansions
    
    meal_function = next(func for func in rules if rules[func][-1].strip() == start_symbol)
    meal_components = rules[meal_function][:-1]  # Exclude the final 'Meal'
    
    sentences = []
    for combination in itertools.product(*[expand(comp.strip()) for comp in meal_components]):
        sentence = f"{meal_function} " + " ".join([item for sublist in combination for item in sublist])
        sentences.append(sentence)
    
    return sentences[:100]  # Limit to 100 sentences for practicality

def create_mermaid_flowchart(sentences):
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
    categories, rules = parse_gf_file(gf_file_path)
    sentences = generate_sentences(categories, rules)
    
    print("Generated sentences (limited to 100):")
    for sentence in sentences:
        print(sentence)
    
    flowchart = create_mermaid_flowchart(sentences)
    flowchart.render('sentence_permutations', format='png', cleanup=True)
    print("\nMermaid flowchart has been saved as 'sentence_permutations.png'")

if __name__ == "__main__":
    gf_file_path = input("Enter the path to your GF file: ")
    main(gf_file_path)