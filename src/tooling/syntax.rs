/// Syntax highlighting definitions (Task 56)

/// Generate TextMate grammar for .seuss files
pub fn generate_textmate_grammar() -> String {
    serde_json::json!({
        "name": "Seuss",
        "scopeName": "source.seuss",
        "fileTypes": ["seuss"],
        "patterns": [
            {
                "name": "comment.line.double-slash.seuss",
                "match": "//.*$"
            },
            {
                "name": "keyword.control.seuss",
                "match": "\\b(timeline|entity|rel|type|if|else|for|in|fn|return|import|let)\\b"
            },
            {
                "name": "keyword.other.seuss",
                "match": "\\b(linear|branch|parallel|loop|nested)\\b"
            },
            {
                "name": "support.type.seuss",
                "match": "\\b(character|event|location|artifact|faction|int|float|string|bool|date)\\b"
            },
            {
                "name": "constant.language.seuss",
                "match": "\\b(true|false|null)\\b"
            },
            {
                "name": "constant.numeric.seuss",
                "match": "\\b\\d+(\\.\\d+)?\\b"
            },
            {
                "name": "string.quoted.double.seuss",
                "begin": "\"",
                "end": "\"",
                "patterns": [
                    { "name": "constant.character.escape.seuss", "match": "\\\\." },
                    { "name": "variable.other.interpolation.seuss", "match": "\\{[^}]+\\}" }
                ]
            },
            {
                "name": "constant.other.date.seuss",
                "match": "\\d{4}-\\d{2}-\\d{2}"
            },
            {
                "name": "keyword.operator.arrow.seuss",
                "match": "-->|->|-\\[|\\]->"
            },
            {
                "name": "keyword.operator.seuss",
                "match": "\\+|-|\\*|/|==|!=|<|>|<=|>=|&&|\\|\\||!"
            },
            {
                "name": "punctuation.definition.block.seuss",
                "match": "[{}\\[\\]();,:]"
            },
            {
                "name": "variable.other.seuss",
                "match": "@\\w+"
            }
        ]
    }).to_string()
}

/// Generate tree-sitter grammar highlights.scm for .seuss files
pub fn generate_treesitter_highlights() -> String {
    r#"; Seuss tree-sitter highlights

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
