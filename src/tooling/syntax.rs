/// Syntax highlighting definitions (Task 56)

/// Generate TextMate grammar for .chron files
pub fn generate_textmate_grammar() -> String {
    serde_json::json!({
        "name": "Chron",
        "scopeName": "source.chron",
        "fileTypes": ["chron"],
        "patterns": [
            {
                "name": "comment.line.double-slash.chron",
                "match": "//.*$"
            },
            {
                "name": "keyword.control.chron",
                "match": "\\b(timeline|entity|rel|type|if|else|for|in|fn|return|import|let)\\b"
            },
            {
                "name": "keyword.other.chron",
                "match": "\\b(linear|branch|parallel|loop|nested)\\b"
            },
            {
                "name": "support.type.chron",
                "match": "\\b(character|event|location|artifact|faction|int|float|string|bool|date)\\b"
            },
            {
                "name": "constant.language.chron",
                "match": "\\b(true|false|null)\\b"
            },
            {
                "name": "constant.numeric.chron",
                "match": "\\b\\d+(\\.\\d+)?\\b"
            },
            {
                "name": "string.quoted.double.chron",
                "begin": "\"",
                "end": "\"",
                "patterns": [
                    { "name": "constant.character.escape.chron", "match": "\\\\." },
                    { "name": "variable.other.interpolation.chron", "match": "\\{[^}]+\\}" }
                ]
            },
            {
                "name": "constant.other.date.chron",
                "match": "\\d{4}-\\d{2}-\\d{2}"
            },
            {
                "name": "keyword.operator.arrow.chron",
                "match": "-->|->|-\\[|\\]->"
            },
            {
                "name": "keyword.operator.chron",
                "match": "\\+|-|\\*|/|==|!=|<|>|<=|>=|&&|\\|\\||!"
            },
            {
                "name": "punctuation.definition.block.chron",
                "match": "[{}\\[\\]();,:]"
            },
            {
                "name": "variable.other.chron",
                "match": "@\\w+"
            }
        ]
    }).to_string()
}

/// Generate tree-sitter grammar highlights.scm for .chron files
pub fn generate_treesitter_highlights() -> String {
    r#"; Chron tree-sitter highlights

(comment) @comment

["timeline" "entity" "rel" "type" "if" "else" "for" "in" "fn" "return" "import" "let"] @keyword

["linear" "branch" "parallel" "loop" "nested"] @type.qualifier

["character" "event" "location" "artifact" "faction"] @type.builtin
["int" "float" "string" "bool" "date"] @type

["true" "false" "null"] @constant.builtin

(number) @number
(string) @string
(date) @constant
(interpolation) @embedded

["-->" "->" "-[" "]->" "-->"] @operator
["+" "-" "*" "/" "==" "!=" "<" ">" "<=" ">=" "&&" "||" "!"] @operator

["(" ")" "{" "}" "[" "]" ";" "," ":"] @punctuation

(identifier) @variable
(meta_attribute) @attribute
"#.to_string()
}
