use std::collections::HashMap;

/// Source span for error reporting (Task 14)
#[derive(Debug, Clone, PartialEq)]
pub struct Span {
    pub start: usize,
    pub end: usize,
    pub file: String,
}

impl Span {
    pub fn new(start: usize, end: usize, file: &str) -> Self {
        Self { start, end, file: file.to_string() }
    }
}

/// Spanned wrapper
#[derive(Debug, Clone)]
pub struct Spanned<T> {
    pub node: T,
    pub span: Span,
}

impl<T> Spanned<T> {
    pub fn new(node: T, span: Span) -> Self {
        Self { node, span }
    }
}

/// Complete AST node enum (Task 13)
pub type Program = Vec<Spanned<Stmt>>;

#[derive(Debug, Clone)]
pub enum Stmt {
    TimelineDecl(TimelineDecl),
    EntityDecl(EntityDecl),
    RelDecl(RelDecl),
    TypeDecl(TypeDecl),
    FnDecl(FnDecl),
    LetStmt(LetStmt),
    Import(String),
    If(IfExpr),
    Match(MatchExpr),
    ForLoop(ForLoop),
    WhileLoop(WhileLoop),
    RepeatLoop(RepeatLoop),
    ExprStmt(Spanned<Expr>),
}

// --- Timeline (Task 2 AST) ---
#[derive(Debug, Clone)]
pub struct TimelineDecl {
    pub name: String,
    pub kind: TimelineKind,
    pub start: Option<Spanned<Expr>>,
    pub end: Option<Spanned<Expr>>,
    pub parent: Option<String>,
    pub fork_from: Option<(String, Spanned<Expr>)>,
    pub merge_into: Option<(String, Spanned<Expr>)>,
    pub loop_count: Option<Spanned<Expr>>,
    pub body: Vec<Spanned<Stmt>>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum TimelineKind {
    Linear,
    Branch,
    Parallel,
    Loop,
}

// --- Entity (Task 3 AST) ---
#[derive(Debug, Clone)]
pub struct EntityDecl {
    pub name: String,
    pub type_ref: Option<String>,
    pub fields: Vec<(String, Spanned<Expr>)>,
    pub appears_on: Vec<(String, Spanned<Expr>, Spanned<Expr>)>,
}

// --- Relationship (Task 4 AST) ---
#[derive(Debug, Clone)]
pub struct RelDecl {
    pub source: String,
    pub target: String,
    pub label: Option<String>,
    pub directed: bool,
    pub temporal_scope: Option<(Spanned<Expr>, Spanned<Expr>)>,
}

// --- Conditionals (Task 6 AST) ---
#[derive(Debug, Clone)]
pub struct IfExpr {
    pub condition: Box<Spanned<Expr>>,
    pub then_block: Block,
    pub else_if_branches: Vec<(Spanned<Expr>, Block)>,
    pub else_block: Option<Block>,
}

#[derive(Debug, Clone)]
pub struct MatchExpr {
    pub subject: Box<Spanned<Expr>>,
    pub arms: Vec<MatchArm>,
}

#[derive(Debug, Clone)]
pub struct MatchArm {
    pub pattern: Spanned<Pattern>,
    pub body: Block,
}

#[derive(Debug, Clone)]
pub enum Pattern {
    Literal(Literal),
    Ident(String),
    Wildcard,
}

// --- Loops (Task 7 AST) ---
#[derive(Debug, Clone)]
pub struct ForLoop {
    pub var: String,
    pub iterable: Box<Spanned<Expr>>,
    pub body: Block,
}

#[derive(Debug, Clone)]
pub struct WhileLoop {
    pub condition: Box<Spanned<Expr>>,
    pub body: Block,
}

#[derive(Debug, Clone)]
pub struct RepeatLoop {
    pub count: Box<Spanned<Expr>>,
    pub body: Block,
}

// --- Variables (Task 8 AST) ---
#[derive(Debug, Clone)]
pub struct LetStmt {
    pub name: String,
    pub mutable: bool,
    pub type_ann: Option<String>,
    pub value: Box<Spanned<Expr>>,
}

// --- Functions (Task 9 AST) ---
#[derive(Debug, Clone)]
pub struct FnDecl {
    pub name: String,
    pub params: Vec<Param>,
    pub return_type: Option<String>,
    pub body: Block,
}

#[derive(Debug, Clone)]
pub struct Param {
    pub name: String,
    pub type_ann: String,
}

// --- Types (Task 10 AST) ---
#[derive(Debug, Clone)]
pub struct TypeDecl {
    pub name: String,
    pub parent: Option<String>,
    pub fields: Vec<TypeField>,
    pub meta: HashMap<String, Spanned<Expr>>,
}

#[derive(Debug, Clone)]
pub struct TypeField {
    pub name: String,
    pub type_ann: String,
    pub optional: bool,
}

// --- Expressions ---
pub type Block = Vec<Spanned<Stmt>>;

#[derive(Debug, Clone)]
pub enum Expr {
    Literal(Literal),
    Ident(String),
    BinOp {
        op: BinOp,
        left: Box<Spanned<Expr>>,
        right: Box<Spanned<Expr>>,
    },
    UnaryOp {
        op: UnaryOp,
        operand: Box<Spanned<Expr>>,
    },
    Call {
        callee: Box<Spanned<Expr>>,
        args: Vec<Spanned<Expr>>,
    },
    FieldAccess {
        object: Box<Spanned<Expr>>,
        field: String,
    },
    Index {
        object: Box<Spanned<Expr>>,
        index: Box<Spanned<Expr>>,
    },
    List(Vec<Spanned<Expr>>),
    Range {
        start: Box<Spanned<Expr>>,
        end: Box<Spanned<Expr>>,
    },
    TimeAt {
        entity: String,
        time: Box<Spanned<Expr>>,
    },
    Closure {
        params: Vec<Param>,
        body: Box<Spanned<Expr>>,
    },
    Block(Block),
    If(Box<IfExpr>),
    Match(Box<MatchExpr>),
}

#[derive(Debug, Clone)]
pub enum Literal {
    Int(i64),
    Float(f64),
    String(String),
    Bool(bool),
    Date(String),
    Duration(i64, String),
}

#[derive(Debug, Clone, PartialEq)]
pub enum BinOp {
    Add, Sub, Mul, Div,
    Eq, Neq, Lt, Gt, Lte, Gte,
    And, Or,
    Range,
}

#[derive(Debug, Clone, PartialEq)]
pub enum UnaryOp {
    Neg,
    Not,
}
