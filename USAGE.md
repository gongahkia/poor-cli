# Seuss Usage

## Installation

```bash
git clone https://github.com/gongahkia/seuss
cd seuss
python3 -m venv senv && source senv/bin/activate
pip install -r requirements.txt
```

## Commands

### Generate Sentences
```bash
python3 src/main.py generate --abstract grammers/caifan/caifan.gf --concrete grammers/caifan/parklane.gf
```
Options: `-f png|pdf|svg|ascii`, `-l <limit>`, `--filter <pattern>`, `--deduplicate`

### Grammar Stats
```bash
python3 src/main.py stats grammers/caifan/caifan.gf
```

### Validate Grammar
```bash
python3 src/main.py validate grammers/caifan/caifan.gf
```

### Lint Grammar
```bash
python3 src/main.py lint grammers/caifan/caifan.gf
python3 src/main.py lint grammers/caifan/caifan.gf --json
```

### Export Grammar
```bash
python3 src/main.py export grammers/caifan/caifan.gf -f json
python3 src/main.py export grammers/caifan/caifan.gf -f latex -o grammar.tex
python3 src/main.py export grammers/caifan/caifan.gf -f html -o grammar.html
```

### Import from EBNF/BNF
```bash
python3 src/main.py import grammar.ebnf -o output.gf
python3 src/main.py import grammar.bnf -n MyGrammar -o output.gf
```

### Dependency Graph
```bash
python3 src/main.py depgraph grammers/caifan/caifan.gf -o deps -f png
```

### Test Suite Generation
```bash
python3 src/main.py testgen --abstract grammers/caifan/caifan.gf --concrete grammers/caifan/parklane.gf -f json
python3 src/main.py testgen --abstract grammers/caifan/caifan.gf --concrete grammers/caifan/parklane.gf -f pytest -o tests.py
```
Options: `-d <depth>`, `-n <max-tests>`

### Parallel Generation (Multilingual)
```bash
python3 src/main.py parallel --abstract grammers/caifan/caifan.gf --concrete grammers/caifan/parklane.gf grammers/caifan/english.gf -n 10
```
Options: `-f table|markdown|json`

### Ambiguity Detection
```bash
python3 src/main.py ambiguity --abstract grammar.gf --concrete concrete.gf "your sentence here"
```

### Exhaustive Generation
```bash
python3 src/main.py exhaust --abstract grammers/caifan/caifan.gf --concrete grammers/caifan/parklane.gf -d 5
```

### Merge Grammars
```bash
python3 src/main.py merge grammar1.gf grammar2.gf -n MergedGrammar -o merged.gf
```

### Interactive REPL
```bash
python3 src/main.py repl --abstract grammers/caifan/caifan.gf --concrete grammers/caifan/parklane.gf
```

### Web UI
```bash
python3 src/main.py web -p 8080
```
Open `http://localhost:8080` in browser.

### Watch Mode
```bash
python3 src/main.py watch --abstract grammers/caifan/caifan.gf --concrete grammers/caifan/parklane.gf
```

### Other Commands
- `diff` - Compare two grammars
- `parse` - Check if sentence matches grammar
- `sample` - Generate N random sentences
- `minimize` - Remove unreachable rules
- `batch` - Process directory of .gf files
- `template` - Generate new grammar template
- `subgraph` - Extract subgraph from category
- `complexity` - Analyze grammar complexity
