# src/web.py

"""Interactive web UI for browser-based grammar exploration."""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import tempfile

from .parser import parse_grammar
from .grammar import AbstractGrammar, ConcreteGrammar
from .generation import generate_random_ast, linearize, generate_exhaustive_asts
from .analysis import calculate_complexity, validate_grammar
from .types import Category


def create_web_ui_html():
    """Generate the HTML for the web UI."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seuss Grammar Explorer</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        h1 { color: #333; margin-bottom: 1.5rem; }
        .panel { background: white; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .panel h2 { color: #444; margin-bottom: 1rem; font-size: 1.2rem; }
        label { display: block; margin-bottom: 0.5rem; font-weight: 500; color: #555; }
        textarea { width: 100%; height: 200px; padding: 0.75rem; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 14px; resize: vertical; }
        button { background: #4a90d9; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 4px; cursor: pointer; font-size: 1rem; margin-right: 0.5rem; margin-top: 0.5rem; }
        button:hover { background: #357abd; }
        button.secondary { background: #6c757d; }
        button.secondary:hover { background: #545b62; }
        .output { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 4px; padding: 1rem; margin-top: 1rem; font-family: monospace; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-top: 1rem; }
        .stat { background: #e3f2fd; padding: 1rem; border-radius: 4px; text-align: center; }
        .stat-value { font-size: 1.5rem; font-weight: bold; color: #1976d2; }
        .stat-label { font-size: 0.85rem; color: #666; }
        .flex { display: flex; gap: 1rem; }
        .flex > * { flex: 1; }
        .error { color: #d32f2f; background: #ffebee; padding: 0.75rem; border-radius: 4px; }
        .success { color: #2e7d32; background: #e8f5e9; padding: 0.75rem; border-radius: 4px; }
        #sentences { list-style: none; }
        #sentences li { padding: 0.5rem; border-bottom: 1px solid #eee; }
        #sentences li:hover { background: #f5f5f5; }
        input[type="number"] { width: 80px; padding: 0.5rem; border: 1px solid #ddd; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Seuss Grammar Explorer</h1>

        <div class="flex">
            <div class="panel">
                <h2>Abstract Grammar</h2>
                <textarea id="abstract" placeholder="abstract MyGrammar

cat
  Sentence ;
  Subject ;
  Verb ;

fun
  MakeSentence : Subject -> Verb -> Sentence ;
  John : Subject ;
  Mary : Subject ;
  Runs : Verb ;
  Walks : Verb ;"></textarea>
            </div>
            <div class="panel">
                <h2>Concrete Grammar</h2>
                <textarea id="concrete" placeholder="concrete MyGrammarEng of MyGrammar = {

lincat
  Sentence = Str ;
  Subject = Str ;
  Verb = Str ;

lin
  MakeSentence s v = s ++ v ;
  John = &quot;John&quot; ;
  Mary = &quot;Mary&quot; ;
  Runs = &quot;runs&quot; ;
  Walks = &quot;walks&quot; ;
}"></textarea>
            </div>
        </div>

        <div class="panel">
            <h2>Actions</h2>
            <button onclick="generateSentences()">Generate Sentences</button>
            <button onclick="showStats()" class="secondary">Show Stats</button>
            <button onclick="validateGrammar()" class="secondary">Validate</button>
            <button onclick="exhaustiveGenerate()" class="secondary">Exhaustive</button>
            <span style="margin-left: 1rem;">
                <label style="display: inline;">Count: <input type="number" id="count" value="10" min="1" max="100"></label>
                <label style="display: inline; margin-left: 1rem;">Depth: <input type="number" id="depth" value="5" min="1" max="10"></label>
            </span>
        </div>

        <div class="panel" id="results-panel" style="display: none;">
            <h2>Results</h2>
            <div id="results"></div>
        </div>
    </div>

    <script>
        async function apiCall(action, data) {
            const response = await fetch('/api', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action, ...data })
            });
            return response.json();
        }

        function showResults(content, isError = false) {
            const panel = document.getElementById('results-panel');
            const results = document.getElementById('results');
            panel.style.display = 'block';
            results.innerHTML = `<div class="${isError ? 'error' : 'output'}">${content}</div>`;
        }

        async function generateSentences() {
            const abstract = document.getElementById('abstract').value;
            const concrete = document.getElementById('concrete').value;
            const count = parseInt(document.getElementById('count').value) || 10;

            try {
                const result = await apiCall('generate', { abstract, concrete, count });
                if (result.error) {
                    showResults(result.error, true);
                } else {
                    const html = '<ul id="sentences">' + result.sentences.map((s, i) =>
                        `<li><strong>${i+1}.</strong> ${s}</li>`
                    ).join('') + '</ul>';
                    showResults(html);
                }
            } catch (e) {
                showResults('Error: ' + e.message, true);
            }
        }

        async function showStats() {
            const abstract = document.getElementById('abstract').value;

            try {
                const result = await apiCall('stats', { abstract });
                if (result.error) {
                    showResults(result.error, true);
                } else {
                    const html = `<div class="stats">
                        <div class="stat"><div class="stat-value">${result.categories}</div><div class="stat-label">Categories</div></div>
                        <div class="stat"><div class="stat-value">${result.functions}</div><div class="stat-label">Functions</div></div>
                        <div class="stat"><div class="stat-value">${result.complexity.branching_factor}</div><div class="stat-label">Branching Factor</div></div>
                        <div class="stat"><div class="stat-value">${result.complexity.max_depth}</div><div class="stat-label">Max Depth</div></div>
                        <div class="stat"><div class="stat-value">${result.complexity.estimated_sentences}</div><div class="stat-label">Est. Sentences</div></div>
                    </div>`;
                    showResults(html);
                }
            } catch (e) {
                showResults('Error: ' + e.message, true);
            }
        }

        async function validateGrammar() {
            const abstract = document.getElementById('abstract').value;

            try {
                const result = await apiCall('validate', { abstract });
                if (result.error) {
                    showResults(result.error, true);
                } else if (result.warnings.length === 0) {
                    showResults('<div class="success">Grammar is valid! No issues found.</div>');
                } else {
                    showResults('Warnings:\\n' + result.warnings.join('\\n'), true);
                }
            } catch (e) {
                showResults('Error: ' + e.message, true);
            }
        }

        async function exhaustiveGenerate() {
            const abstract = document.getElementById('abstract').value;
            const concrete = document.getElementById('concrete').value;
            const depth = parseInt(document.getElementById('depth').value) || 5;

            try {
                const result = await apiCall('exhaust', { abstract, concrete, depth });
                if (result.error) {
                    showResults(result.error, true);
                } else {
                    const html = `<p><strong>Total: ${result.sentences.length} sentences</strong></p>
                        <ul id="sentences">` + result.sentences.map((s, i) =>
                        `<li><strong>${i+1}.</strong> ${s}</li>`
                    ).join('') + '</ul>';
                    showResults(html);
                }
            } catch (e) {
                showResults('Error: ' + e.message, true);
            }
        }
    </script>
</body>
</html>'''


class SeussHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for the Seuss web UI."""

    def __init__(self, *args, grammars_dir=None, **kwargs):
        self.grammars_dir = grammars_dir
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(create_web_ui_html().encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/api':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            result = self.handle_api(data)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_error(404)

    def handle_api(self, data):
        action = data.get('action')

        try:
            if action == 'generate':
                return self.api_generate(data)
            elif action == 'stats':
                return self.api_stats(data)
            elif action == 'validate':
                return self.api_validate(data)
            elif action == 'exhaust':
                return self.api_exhaust(data)
            else:
                return {'error': f'Unknown action: {action}'}
        except Exception as e:
            return {'error': str(e)}

    def api_generate(self, data):
        abstract_grammar = self._parse_abstract(data['abstract'])
        concrete_grammar = self._parse_concrete(data['concrete'])
        count = data.get('count', 10)

        sentences = []
        for _ in range(count):
            ast = generate_random_ast(abstract_grammar, Category("Sentence"))
            if ast:
                sentences.append(linearize(ast, concrete_grammar))

        return {'sentences': sentences}

    def api_stats(self, data):
        abstract_grammar = self._parse_abstract(data['abstract'])
        complexity = calculate_complexity(abstract_grammar)

        return {
            'categories': len(abstract_grammar.categories),
            'functions': len(abstract_grammar.functions),
            'complexity': complexity
        }

    def api_validate(self, data):
        abstract_grammar = self._parse_abstract(data['abstract'])
        warnings = validate_grammar(abstract_grammar)
        return {'warnings': warnings}

    def api_exhaust(self, data):
        abstract_grammar = self._parse_abstract(data['abstract'])
        concrete_grammar = self._parse_concrete(data['concrete'])
        depth = data.get('depth', 5)

        asts = generate_exhaustive_asts(abstract_grammar, Category("Sentence"), depth)
        sentences = [linearize(ast, concrete_grammar) for ast in asts]

        return {'sentences': sentences}

    def _parse_abstract(self, content):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gf', delete=False) as f:
            f.write(content)
            f.flush()
            grammar = parse_grammar(f.name, use_cache=False)
            os.unlink(f.name)
            return grammar

    def _parse_concrete(self, content):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gf', delete=False) as f:
            f.write(content)
            f.flush()
            grammar = parse_grammar(f.name, use_cache=False)
            os.unlink(f.name)
            return grammar

    def log_message(self, format, *args):
        pass  # Suppress logging


def start_web_server(port=8080, grammars_dir=None):
    """Start the Seuss web UI server."""

    def handler(*args, **kwargs):
        return SeussHandler(*args, grammars_dir=grammars_dir, **kwargs)

    server = HTTPServer(('localhost', port), handler)
    print(f"Seuss Web UI running at http://localhost:{port}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.shutdown()
