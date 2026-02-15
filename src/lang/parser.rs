use pest::iterators::Pair;
use pest::Parser;
use pest_derive::Parser;

use super::ast::*;

#[derive(Parser)]
#[grammar = "lang/seuss.pest"]
pub struct SeussParser;

/// Parse error with location context (Task 15)
#[derive(Debug, Clone)]
pub struct ParseError {
    pub message: String,
    pub span: Span,
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[{}:{}..{}] {}",
            self.span.file, self.span.start, self.span.end, self.message
        )
    }
}

pub fn parse_program(source: &str, file: &str) -> Result<Program, Vec<ParseError>> {
    let pairs = SeussParser::parse(Rule::program, source).map_err(|e| {
        vec![ParseError {
            message: e.to_string(),
            span: Span::new(0, 0, file),
        }]
    })?;

    let mut stmts = Vec::new();
    let mut errors = Vec::new();

    for pair in pairs {
        if pair.as_rule() == Rule::program {
            for inner in pair.into_inner() {
                if inner.as_rule() == Rule::EOI {
                    continue;
                }
                match parse_stmt(inner, file) {
                    Ok(s) => stmts.push(s),
                    Err(e) => errors.push(e),
                }
            }
        }
    }

    if errors.is_empty() {
        Ok(stmts)
    } else {
        Err(errors)
    }
}

fn span_from(pair: &Pair<Rule>, file: &str) -> Span {
    let s = pair.as_span();
    Span::new(s.start(), s.end(), file)
}

fn parse_stmt(pair: Pair<Rule>, file: &str) -> Result<Spanned<Stmt>, ParseError> {
    let sp = span_from(&pair, file);
    let rule = pair.as_rule();

    // If this pair IS already a specific statement type, handle directly
    if rule != Rule::stmt {
        return parse_stmt_inner(pair, file, sp);
    }

    let inner = pair.into_inner().next().ok_or_else(|| ParseError {
        message: "empty statement".into(),
        span: sp.clone(),
    })?;
    let stmt = match inner.as_rule() {
        Rule::timeline_decl => Stmt::TimelineDecl(parse_timeline_decl(inner, file)?),
        Rule::entity_decl => Stmt::EntityDecl(parse_entity_decl(inner, file)?),
        Rule::rel_decl => Stmt::RelDecl(parse_rel_decl(inner, file)?),
        Rule::type_decl => Stmt::TypeDecl(parse_type_decl(inner, file)?),
        Rule::fn_decl => Stmt::FnDecl(parse_fn_decl(inner, file)?),
        Rule::let_stmt => Stmt::LetStmt(parse_let_stmt(inner, file)?),
        Rule::import_stmt => {
            let s = inner.into_inner().next().ok_or_else(|| ParseError {
                message: "expected import path".into(),
                span: sp.clone(),
            })?;
            Stmt::Import(parse_string_value(s))
        }
        Rule::if_expr => Stmt::If(parse_if_expr(inner, file)?),
        Rule::match_expr => Stmt::Match(parse_match_expr(inner, file)?),
        Rule::for_loop => Stmt::ForLoop(parse_for_loop(inner, file)?),
        Rule::while_loop => Stmt::WhileLoop(parse_while_loop(inner, file)?),
        Rule::repeat_loop => Stmt::RepeatLoop(parse_repeat_loop(inner, file)?),
        Rule::assign_stmt => {
            let mut ai = inner.into_inner();
            let name = ai
                .next()
                .ok_or_else(|| ParseError {
                    message: "expected assignment target".into(),
                    span: sp.clone(),
                })?
                .as_str()
                .to_string();
            let value = parse_expr(
                ai.next().ok_or_else(|| ParseError {
                    message: "expected assignment value".into(),
                    span: sp.clone(),
                })?,
                file,
            )?;
            Stmt::Assign { name, value }
        }
        Rule::expr_stmt => {
            let e = parse_expr(
                inner.into_inner().next().ok_or_else(|| ParseError {
                    message: "expected expression".into(),
                    span: sp.clone(),
                })?,
                file,
            )?;
            Stmt::ExprStmt(e)
        }
        _ => {
            return Err(ParseError {
                message: format!("unexpected rule: {:?}", inner.as_rule()),
                span: span_from(&inner, file),
            });
        }
    };
    Ok(Spanned::new(stmt, sp))
}

fn parse_timeline_decl(pair: Pair<Rule>, file: &str) -> Result<TimelineDecl, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let name = inner
        .next()
        .ok_or_else(|| ParseError {
            message: "expected timeline name".into(),
            span: sp.clone(),
        })?
        .as_str()
        .to_string();
    let mut decl = TimelineDecl {
        name,
        kind: TimelineKind::Linear,
        start: None,
        end: None,
        parent: None,
        fork_from: None,
        merge_into: None,
        loop_count: None,
        body: Vec::new(),
    };

    for field in inner {
        if field.as_rule() != Rule::timeline_field {
            continue;
        }
        let mut parts = field.into_inner();
        let first = match parts.next() {
            Some(f) => f,
            None => continue,
        };
        match first.as_str() {
            "kind" => {
                if let Some(k) = parts.next() {
                    decl.kind = match k.as_str() {
                        "branch" => TimelineKind::Branch,
                        "parallel" => TimelineKind::Parallel,
                        "loop" => TimelineKind::Loop,
                        _ => TimelineKind::Linear,
                    };
                }
            }
            "start" => {
                if let Some(e) = parts.next() {
                    decl.start = Some(parse_expr(e, file)?);
                }
            }
            "end" => {
                if let Some(e) = parts.next() {
                    decl.end = Some(parse_expr(e, file)?);
                }
            }
            "parent" => {
                if let Some(p) = parts.next() {
                    decl.parent = Some(p.as_str().to_string());
                }
            }
            "fork_from" => {
                let tl = parts
                    .next()
                    .ok_or_else(|| ParseError {
                        message: "expected fork_from timeline".into(),
                        span: sp.clone(),
                    })?
                    .as_str()
                    .to_string();
                let at = parse_expr(
                    parts.next().ok_or_else(|| ParseError {
                        message: "expected fork_from time".into(),
                        span: sp.clone(),
                    })?,
                    file,
                )?;
                decl.fork_from = Some((tl, at));
            }
            "merge_into" => {
                let tl = parts
                    .next()
                    .ok_or_else(|| ParseError {
                        message: "expected merge_into timeline".into(),
                        span: sp.clone(),
                    })?
                    .as_str()
                    .to_string();
                let at = parse_expr(
                    parts.next().ok_or_else(|| ParseError {
                        message: "expected merge_into time".into(),
                        span: sp.clone(),
                    })?,
                    file,
                )?;
                decl.merge_into = Some((tl, at));
            }
            "loop_count" => {
                if let Some(e) = parts.next() {
                    decl.loop_count = Some(parse_expr(e, file)?);
                }
            }
            _ => {
                // Treat as a stmt in body
                if let Ok(s) = parse_stmt(first, file) {
                    decl.body.push(s);
                }
            }
        }
    }
    Ok(decl)
}

fn parse_entity_decl(pair: Pair<Rule>, file: &str) -> Result<EntityDecl, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let name = inner
        .next()
        .ok_or_else(|| ParseError {
            message: "expected entity name".into(),
            span: sp.clone(),
        })?
        .as_str()
        .to_string();
    let mut type_ref = None;
    let mut fields = Vec::new();
    let mut appears_on = Vec::new();

    for part in inner {
        match part.as_rule() {
            Rule::type_ref => {
                type_ref = Some(
                    part.into_inner()
                        .next()
                        .ok_or_else(|| ParseError {
                            message: "expected type reference".into(),
                            span: sp.clone(),
                        })?
                        .as_str()
                        .to_string(),
                );
            }
            Rule::entity_field => {
                let mut fi = part.into_inner();
                let first = fi.next().ok_or_else(|| ParseError {
                    message: "expected entity field".into(),
                    span: sp.clone(),
                })?;
                if first.as_str() == "appears_on" {
                    let timeline = fi
                        .next()
                        .ok_or_else(|| ParseError {
                            message: "expected timeline name".into(),
                            span: sp.clone(),
                        })?
                        .as_str()
                        .to_string();
                    let range = fi.next().ok_or_else(|| ParseError {
                        message: "expected time range".into(),
                        span: sp.clone(),
                    })?;
                    let mut ri = range.into_inner();
                    let start = parse_expr(
                        ri.next().ok_or_else(|| ParseError {
                            message: "expected range start".into(),
                            span: sp.clone(),
                        })?,
                        file,
                    )?;
                    let end = parse_expr(
                        ri.next().ok_or_else(|| ParseError {
                            message: "expected range end".into(),
                            span: sp.clone(),
                        })?,
                        file,
                    )?;
                    appears_on.push((timeline, start, end));
                } else {
                    let fname = first.as_str().to_string();
                    let val = parse_expr(
                        fi.next().ok_or_else(|| ParseError {
                            message: "expected field value".into(),
                            span: sp.clone(),
                        })?,
                        file,
                    )?;
                    fields.push((fname, val));
                }
            }
            _ => {}
        }
    }

    Ok(EntityDecl {
        name,
        type_ref,
        fields,
        appears_on,
    })
}

fn parse_rel_decl(pair: Pair<Rule>, file: &str) -> Result<RelDecl, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let source = inner
        .next()
        .ok_or_else(|| ParseError {
            message: "expected relation source".into(),
            span: sp.clone(),
        })?
        .as_str()
        .to_string();
    let arrow = inner.next().ok_or_else(|| ParseError {
        message: "expected relation arrow".into(),
        span: sp.clone(),
    })?;
    let arrow_str = arrow.as_str();
    let (label, directed) = if arrow_str.starts_with("-[") {
        let lbl = arrow.into_inner().next().map(|s| parse_string_value(s));
        let dir = arrow_str.ends_with("->");
        (lbl, dir)
    } else {
        (None, arrow_str.contains('>'))
    };
    let target = inner
        .next()
        .ok_or_else(|| ParseError {
            message: "expected relation target".into(),
            span: sp.clone(),
        })?
        .as_str()
        .to_string();
    let temporal_scope = if let Some(range) = inner.next() {
        if range.as_rule() == Rule::time_range_expr {
            let mut ri = range.into_inner();
            let start = parse_expr(
                ri.next().ok_or_else(|| ParseError {
                    message: "expected range start".into(),
                    span: sp.clone(),
                })?,
                file,
            )?;
            let end = parse_expr(
                ri.next().ok_or_else(|| ParseError {
                    message: "expected range end".into(),
                    span: sp.clone(),
                })?,
                file,
            )?;
            Some((start, end))
        } else {
            None
        }
    } else {
        None
    };

    Ok(RelDecl {
        source,
        target,
        label,
        directed,
        temporal_scope,
    })
}

fn parse_type_decl(pair: Pair<Rule>, file: &str) -> Result<TypeDecl, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let name = inner
        .next()
        .ok_or_else(|| ParseError {
            message: "expected type name".into(),
            span: sp.clone(),
        })?
        .as_str()
        .to_string();
    let mut parent = None;
    let mut fields = Vec::new();
    let mut meta = std::collections::HashMap::new();

    for part in inner {
        match part.as_rule() {
            Rule::type_ref => {
                parent = Some(
                    part.into_inner()
                        .next()
                        .ok_or_else(|| ParseError {
                            message: "expected type reference".into(),
                            span: sp.clone(),
                        })?
                        .as_str()
                        .to_string(),
                );
            }
            Rule::type_field => {
                let mut fi = part.into_inner();
                let first = fi.next().ok_or_else(|| ParseError {
                    message: "expected type field".into(),
                    span: sp.clone(),
                })?;
                match first.as_rule() {
                    Rule::meta_attr => {
                        let mut mi = first.into_inner();
                        let key = mi
                            .next()
                            .ok_or_else(|| ParseError {
                                message: "expected meta key".into(),
                                span: sp.clone(),
                            })?
                            .as_str()
                            .to_string();
                        let val = parse_expr(
                            mi.next().ok_or_else(|| ParseError {
                                message: "expected meta value".into(),
                                span: sp.clone(),
                            })?,
                            file,
                        )?;
                        meta.insert(key, val);
                    }
                    Rule::ident => {
                        let fname = first.as_str().to_string();
                        let ta = fi.next().ok_or_else(|| ParseError {
                            message: "expected type annotation".into(),
                            span: sp.clone(),
                        })?;
                        let mut tai = ta.into_inner();
                        let type_name = tai
                            .next()
                            .ok_or_else(|| ParseError {
                                message: "expected type name in annotation".into(),
                                span: sp.clone(),
                            })?
                            .as_str()
                            .to_string();
                        let optional = tai.next().is_some();
                        fields.push(TypeField {
                            name: fname,
                            type_ann: type_name,
                            optional,
                        });
                    }
                    _ => {}
                }
            }
            _ => {}
        }
    }

    Ok(TypeDecl {
        name,
        parent,
        fields,
        meta,
    })
}

fn parse_fn_decl(pair: Pair<Rule>, file: &str) -> Result<FnDecl, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let name = inner
        .next()
        .ok_or_else(|| ParseError {
            message: "expected function name".into(),
            span: sp.clone(),
        })?
        .as_str()
        .to_string();
    let mut params = Vec::new();
    let mut return_type = None;
    let mut body = Vec::new();

    for part in inner {
        match part.as_rule() {
            Rule::param_list => {
                params = parse_param_list(part);
            }
            Rule::type_annotation => {
                return_type = Some(
                    part.into_inner()
                        .next()
                        .ok_or_else(|| ParseError {
                            message: "expected return type".into(),
                            span: sp.clone(),
                        })?
                        .as_str()
                        .to_string(),
                );
            }
            Rule::block => {
                body = parse_block(part, file)?;
            }
            _ => {}
        }
    }

    Ok(FnDecl {
        name,
        params,
        return_type,
        body,
    })
}

fn parse_let_stmt(pair: Pair<Rule>, file: &str) -> Result<LetStmt, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let mut mutable = false;
    let mut name = String::new();
    let mut type_ann = None;
    let mut value = None;

    for part in inner {
        match part.as_rule() {
            Rule::ident => {
                if part.as_str() == "mut" {
                    mutable = true;
                } else {
                    name = part.as_str().to_string();
                }
            }
            Rule::type_annotation => {
                type_ann = Some(
                    part.into_inner()
                        .next()
                        .ok_or_else(|| ParseError {
                            message: "expected type annotation".into(),
                            span: sp.clone(),
                        })?
                        .as_str()
                        .to_string(),
                );
            }
            Rule::expr => {
                value = Some(parse_expr(part, file)?);
            }
            _ => {}
        }
    }

    Ok(LetStmt {
        name,
        mutable,
        type_ann,
        value: Box::new(value.ok_or_else(|| ParseError {
            message: "expected let value".into(),
            span: sp.clone(),
        })?),
    })
}

fn parse_if_expr(pair: Pair<Rule>, file: &str) -> Result<IfExpr, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let condition = Box::new(parse_expr(
        inner.next().ok_or_else(|| ParseError {
            message: "expected if condition".into(),
            span: sp.clone(),
        })?,
        file,
    )?);
    let then_block = parse_block(
        inner.next().ok_or_else(|| ParseError {
            message: "expected then block".into(),
            span: sp.clone(),
        })?,
        file,
    )?;
    let mut else_if_branches = Vec::new();
    let mut else_block = None;

    let remaining: Vec<_> = inner.collect();
    let mut i = 0;
    while i < remaining.len() {
        if remaining[i].as_rule() == Rule::expr {
            let cond = parse_expr(remaining[i].clone(), file)?;
            i += 1;
            let blk = parse_block(remaining[i].clone(), file)?;
            else_if_branches.push((cond, blk));
        } else if remaining[i].as_rule() == Rule::block {
            else_block = Some(parse_block(remaining[i].clone(), file)?);
        }
        i += 1;
    }

    Ok(IfExpr {
        condition,
        then_block,
        else_if_branches,
        else_block,
    })
}

fn parse_match_expr(pair: Pair<Rule>, file: &str) -> Result<MatchExpr, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let subject = Box::new(parse_expr(
        inner.next().ok_or_else(|| ParseError {
            message: "expected match subject".into(),
            span: sp.clone(),
        })?,
        file,
    )?);
    let mut arms = Vec::new();

    for arm_pair in inner {
        if arm_pair.as_rule() == Rule::match_arm {
            let mut ai = arm_pair.into_inner();
            let pat_pair = ai.next().ok_or_else(|| ParseError {
                message: "expected match pattern".into(),
                span: sp.clone(),
            })?;
            let sp = span_from(&pat_pair, file);
            let pat = match pat_pair.as_str() {
                "_" => Pattern::Wildcard,
                s => {
                    let inner_rule = pat_pair.into_inner().next();
                    if let Some(lit) = inner_rule {
                        if lit.as_rule() == Rule::literal {
                            Pattern::Literal(parse_literal(lit)?)
                        } else {
                            Pattern::Ident(s.to_string())
                        }
                    } else {
                        Pattern::Ident(s.to_string())
                    }
                }
            };
            let body_pair = ai.next().ok_or_else(|| ParseError {
                message: "expected match arm body".into(),
                span: sp.clone(),
            })?;
            let body = if body_pair.as_rule() == Rule::block {
                parse_block(body_pair, file)?
            } else {
                let e = parse_expr(body_pair, file)?;
                let esp = e.span.clone();
                vec![Spanned::new(Stmt::ExprStmt(e), esp)]
            };
            arms.push(MatchArm {
                pattern: Spanned::new(pat, sp),
                body,
            });
        }
    }

    Ok(MatchExpr { subject, arms })
}

fn parse_for_loop(pair: Pair<Rule>, file: &str) -> Result<ForLoop, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let var = inner
        .next()
        .ok_or_else(|| ParseError {
            message: "expected loop variable".into(),
            span: sp.clone(),
        })?
        .as_str()
        .to_string();
    let iterable = Box::new(parse_expr(
        inner.next().ok_or_else(|| ParseError {
            message: "expected iterable".into(),
            span: sp.clone(),
        })?,
        file,
    )?);
    let body = parse_block(
        inner.next().ok_or_else(|| ParseError {
            message: "expected loop body".into(),
            span: sp.clone(),
        })?,
        file,
    )?;
    Ok(ForLoop {
        var,
        iterable,
        body,
    })
}

fn parse_while_loop(pair: Pair<Rule>, file: &str) -> Result<WhileLoop, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let condition = Box::new(parse_expr(
        inner.next().ok_or_else(|| ParseError {
            message: "expected while condition".into(),
            span: sp.clone(),
        })?,
        file,
    )?);
    let body = parse_block(
        inner.next().ok_or_else(|| ParseError {
            message: "expected while body".into(),
            span: sp.clone(),
        })?,
        file,
    )?;
    Ok(WhileLoop { condition, body })
}

fn parse_repeat_loop(pair: Pair<Rule>, file: &str) -> Result<RepeatLoop, ParseError> {
    let sp = span_from(&pair, file);
    let mut inner = pair.into_inner();
    let count = Box::new(parse_expr(
        inner.next().ok_or_else(|| ParseError {
            message: "expected repeat count".into(),
            span: sp.clone(),
        })?,
        file,
    )?);
    let body = parse_block(
        inner.next().ok_or_else(|| ParseError {
            message: "expected repeat body".into(),
            span: sp.clone(),
        })?,
        file,
    )?;
    Ok(RepeatLoop { count, body })
}

fn parse_block(pair: Pair<Rule>, file: &str) -> Result<Block, ParseError> {
    let mut stmts = Vec::new();
    for inner in pair.into_inner() {
        match inner.as_rule() {
            Rule::stmt => {
                // Parse inner rule of stmt
                let sp = span_from(&inner, file);
                if let Some(child) = inner.into_inner().next() {
                    match parse_stmt_inner(child, file, sp) {
                        Ok(s) => stmts.push(s),
                        Err(_) => {} // skip errors in blocks for recovery
                    }
                }
            }
            _ => {
                // trailing expression
                if let Ok(e) = parse_expr(inner, file) {
                    let sp = e.span.clone();
                    stmts.push(Spanned::new(Stmt::ExprStmt(e), sp));
                }
            }
        }
    }
    Ok(stmts)
}

fn parse_stmt_inner(pair: Pair<Rule>, file: &str, sp: Span) -> Result<Spanned<Stmt>, ParseError> {
    let stmt = match pair.as_rule() {
        Rule::timeline_decl => Stmt::TimelineDecl(parse_timeline_decl(pair, file)?),
        Rule::entity_decl => Stmt::EntityDecl(parse_entity_decl(pair, file)?),
        Rule::rel_decl => Stmt::RelDecl(parse_rel_decl(pair, file)?),
        Rule::type_decl => Stmt::TypeDecl(parse_type_decl(pair, file)?),
        Rule::fn_decl => Stmt::FnDecl(parse_fn_decl(pair, file)?),
        Rule::let_stmt => Stmt::LetStmt(parse_let_stmt(pair, file)?),
        Rule::assign_stmt => {
            let mut ai = pair.into_inner();
            let name = ai
                .next()
                .ok_or_else(|| ParseError {
                    message: "expected assignment target".into(),
                    span: sp.clone(),
                })?
                .as_str()
                .to_string();
            let value = parse_expr(
                ai.next().ok_or_else(|| ParseError {
                    message: "expected assignment value".into(),
                    span: sp.clone(),
                })?,
                file,
            )?;
            Stmt::Assign { name, value }
        }
        Rule::import_stmt => {
            let s = pair.into_inner().next().ok_or_else(|| ParseError {
                message: "expected import path".into(),
                span: sp.clone(),
            })?;
            Stmt::Import(parse_string_value(s))
        }
        Rule::if_expr => Stmt::If(parse_if_expr(pair, file)?),
        Rule::match_expr => Stmt::Match(parse_match_expr(pair, file)?),
        Rule::for_loop => Stmt::ForLoop(parse_for_loop(pair, file)?),
        Rule::while_loop => Stmt::WhileLoop(parse_while_loop(pair, file)?),
        Rule::repeat_loop => Stmt::RepeatLoop(parse_repeat_loop(pair, file)?),
        Rule::expr_stmt => {
            let e = parse_expr(
                pair.into_inner().next().ok_or_else(|| ParseError {
                    message: "expected expression".into(),
                    span: sp.clone(),
                })?,
                file,
            )?;
            Stmt::ExprStmt(e)
        }
        _ => {
            return Err(ParseError {
                message: format!("unexpected rule in block: {:?}", pair.as_rule()),
                span: sp,
            });
        }
    };
    Ok(Spanned::new(stmt, sp))
}

/// Expression parser with precedence climbing
fn parse_expr(pair: Pair<Rule>, file: &str) -> Result<Spanned<Expr>, ParseError> {
    let sp = span_from(&pair, file);

    match pair.as_rule() {
        Rule::expr => {
            let inner: Vec<_> = pair.into_inner().collect();
            if inner.len() == 1 {
                return parse_expr(
                    inner.into_iter().next().ok_or_else(|| ParseError {
                        message: "empty expression".into(),
                        span: sp.clone(),
                    })?,
                    file,
                );
            }
            let mut operands: Vec<Spanned<Expr>> = Vec::new();
            let mut ops: Vec<BinOp> = Vec::new();
            for (i, item) in inner.into_iter().enumerate() {
                if i % 2 == 0 {
                    operands.push(parse_expr(item, file)?);
                } else {
                    ops.push(parse_bin_op(item.as_str()));
                }
            }
            Ok(build_expr_with_precedence(operands, ops, file))
        }
        Rule::unary_expr => {
            let mut inner: Vec<_> = pair.into_inner().collect();
            if inner.len() == 1 {
                return parse_expr(inner.remove(0), file);
            }
            let op = match inner[0].as_str() {
                "-" => UnaryOp::Neg,
                "!" => UnaryOp::Not,
                _ => UnaryOp::Neg,
            };
            let operand = parse_expr(inner.remove(1), file)?;
            Ok(Spanned::new(
                Expr::UnaryOp {
                    op,
                    operand: Box::new(operand),
                },
                sp,
            ))
        }
        Rule::primary_expr => {
            let mut inner: Vec<_> = pair.into_inner().collect();
            if inner.is_empty() {
                return Err(ParseError {
                    message: "empty primary expr".into(),
                    span: sp,
                });
            }
            let first = inner.remove(0);
            match first.as_rule() {
                Rule::literal => {
                    let lit = parse_literal(first)?;
                    Ok(Spanned::new(Expr::Literal(lit), sp))
                }
                Rule::ident => {
                    let name = first.as_str().to_string();
                    if inner.is_empty() {
                        return Ok(Spanned::new(Expr::Ident(name), sp));
                    }
                    let mut result = Spanned::new(Expr::Ident(name), sp.clone());
                    for next in inner {
                        match next.as_rule() {
                            Rule::call_args => {
                                let args = parse_call_args(next, file)?;
                                let new_sp = Span::new(result.span.start, sp.end, file);
                                result = Spanned::new(
                                    Expr::Call {
                                        callee: Box::new(result),
                                        args,
                                    },
                                    new_sp,
                                );
                            }
                            Rule::ident => {
                                let field = next.as_str().to_string();
                                let new_sp = Span::new(result.span.start, sp.end, file);
                                result = Spanned::new(
                                    Expr::FieldAccess {
                                        object: Box::new(result),
                                        field,
                                    },
                                    new_sp,
                                );
                            }
                            Rule::time_range_expr => {
                                let mut ri = next.into_inner();
                                let start = parse_expr(
                                    ri.next().ok_or_else(|| ParseError {
                                        message: "expected range start".into(),
                                        span: sp.clone(),
                                    })?,
                                    file,
                                )?;
                                let end = parse_expr(
                                    ri.next().ok_or_else(|| ParseError {
                                        message: "expected range end".into(),
                                        span: sp.clone(),
                                    })?,
                                    file,
                                )?;
                                let ent = if let Expr::Ident(n) = &result.node {
                                    n.clone()
                                } else {
                                    String::new()
                                };
                                result = Spanned::new(
                                    Expr::Range {
                                        start: Box::new(start),
                                        end: Box::new(end),
                                    },
                                    sp.clone(),
                                );
                            }
                            _ => {}
                        }
                    }
                    Ok(result)
                }
                Rule::closure_expr => {
                    let mut ci = first.into_inner();
                    let mut params = Vec::new();
                    let mut body_pair = None;
                    for p in ci {
                        match p.as_rule() {
                            Rule::param_list => params = parse_param_list(p),
                            Rule::expr => body_pair = Some(p),
                            _ => {}
                        }
                    }
                    let body = parse_expr(
                        body_pair.ok_or_else(|| ParseError {
                            message: "expected closure body".into(),
                            span: sp.clone(),
                        })?,
                        file,
                    )?;
                    Ok(Spanned::new(
                        Expr::Closure {
                            params,
                            body: Box::new(body),
                        },
                        sp,
                    ))
                }
                Rule::expr => {
                    // parenthesized
                    parse_expr(first, file)
                }
                _ => {
                    // list literal [a, b, c]
                    let mut items = vec![parse_expr(first, file)?];
                    for rest in inner {
                        items.push(parse_expr(rest, file)?);
                    }
                    Ok(Spanned::new(Expr::List(items), sp))
                }
            }
        }
        Rule::time_expr | Rule::time_range_expr => {
            let mut inner = pair.into_inner();
            let first = inner.next().ok_or_else(|| ParseError {
                message: "expected time expression".into(),
                span: sp.clone(),
            })?;
            parse_expr(first, file)
        }
        Rule::literal => {
            let lit = parse_literal(pair)?;
            Ok(Spanned::new(Expr::Literal(lit), sp))
        }
        Rule::ident => Ok(Spanned::new(Expr::Ident(pair.as_str().to_string()), sp)),
        Rule::date_lit => Ok(Spanned::new(
            Expr::Literal(Literal::Date(pair.as_str().to_string())),
            sp,
        )),
        Rule::int_lit => {
            let v: i64 = pair.as_str().parse().unwrap_or(0);
            Ok(Spanned::new(Expr::Literal(Literal::Int(v)), sp))
        }
        Rule::float_lit => {
            let v: f64 = pair.as_str().parse().unwrap_or(0.0);
            Ok(Spanned::new(Expr::Literal(Literal::Float(v)), sp))
        }
        Rule::string_lit => Ok(Spanned::new(
            Expr::Literal(Literal::String(parse_string_value(pair))),
            sp,
        )),
        Rule::bool_lit => Ok(Spanned::new(
            Expr::Literal(Literal::Bool(pair.as_str() == "true")),
            sp,
        )),
        Rule::duration_lit => {
            let s = pair.as_str();
            let num_end = s.find(|c: char| !c.is_ascii_digit()).unwrap_or(s.len());
            let num: i64 = s[..num_end].parse().unwrap_or(0);
            let unit = s[num_end..].to_string();
            Ok(Spanned::new(
                Expr::Literal(Literal::Duration(num, unit)),
                sp,
            ))
        }
        Rule::fuzzy_date => {
            let inner = pair.into_inner().next().ok_or_else(|| ParseError {
                message: "expected fuzzy date".into(),
                span: sp.clone(),
            })?;
            let date_str = format!("~{}", inner.as_str());
            Ok(Spanned::new(Expr::Literal(Literal::Date(date_str)), sp))
        }
        Rule::relative_time => {
            // treat as identifier reference for now
            Ok(Spanned::new(Expr::Ident(pair.as_str().to_string()), sp))
        }
        Rule::era_ref => Ok(Spanned::new(Expr::Ident(pair.as_str().to_string()), sp)),
        _ => Err(ParseError {
            message: format!("unexpected expr rule: {:?}", pair.as_rule()),
            span: sp,
        }),
    }
}

fn parse_call_args(pair: Pair<Rule>, file: &str) -> Result<Vec<Spanned<Expr>>, ParseError> {
    let mut args = Vec::new();
    for inner in pair.into_inner() {
        args.push(parse_expr(inner, file)?);
    }
    Ok(args)
}

fn parse_literal(pair: Pair<Rule>) -> Result<Literal, ParseError> {
    let pair_span = pair.as_span();
    let err_span = Span::new(pair_span.start(), pair_span.end(), "");
    let inner = pair.into_inner().next().ok_or_else(|| ParseError {
        message: "expected literal value".into(),
        span: err_span,
    })?;
    match inner.as_rule() {
        Rule::int_lit => Ok(Literal::Int(inner.as_str().parse().unwrap_or(0))),
        Rule::float_lit => Ok(Literal::Float(inner.as_str().parse().unwrap_or(0.0))),
        Rule::string_lit => Ok(Literal::String(parse_string_value(inner))),
        Rule::date_lit => Ok(Literal::Date(inner.as_str().to_string())),
        Rule::duration_lit => {
            let s = inner.as_str();
            let num_end = s.find(|c: char| !c.is_ascii_digit()).unwrap_or(s.len());
            let num: i64 = s[..num_end].parse().unwrap_or(0);
            let unit = s[num_end..].to_string();
            Ok(Literal::Duration(num, unit))
        }
        Rule::bool_lit => Ok(Literal::Bool(inner.as_str() == "true")),
        _ => Ok(Literal::Int(0)),
    }
}

fn parse_string_value(pair: Pair<Rule>) -> String {
    let raw = pair.as_str();
    let trimmed = &raw[1..raw.len() - 1]; // strip quotes
    trimmed
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\r", "\r")
        .replace("\\\\", "\\")
        .replace("\\\"", "\"")
}

fn parse_param_list(pair: Pair<Rule>) -> Vec<Param> {
    pair.into_inner()
        .filter(|p| p.as_rule() == Rule::param)
        .filter_map(|p| {
            let mut pi = p.into_inner();
            let name = pi.next()?.as_str().to_string();
            let type_ann = pi.next()?.into_inner().next()?.as_str().to_string();
            Some(Param { name, type_ann })
        })
        .collect()
}

fn op_precedence(op: &BinOp) -> u8 {
    match op {
        BinOp::Range => 0,
        BinOp::Or => 1,
        BinOp::And => 2,
        BinOp::Eq | BinOp::Neq | BinOp::Lt | BinOp::Gt | BinOp::Lte | BinOp::Gte => 3,
        BinOp::Add | BinOp::Sub => 4,
        BinOp::Mul | BinOp::Div => 5,
    }
}
fn build_expr_with_precedence(
    mut operands: Vec<Spanned<Expr>>,
    mut ops: Vec<BinOp>,
    file: &str,
) -> Spanned<Expr> {
    for prec in (0..=5).rev() {
        // highest precedence first
        let mut i = 0;
        while i < ops.len() {
            if op_precedence(&ops[i]) == prec {
                let op = ops.remove(i);
                let right = operands.remove(i + 1);
                let left = operands.remove(i);
                let new_sp = Span::new(left.span.start, right.span.end, file);
                operands.insert(
                    i,
                    Spanned::new(
                        Expr::BinOp {
                            op,
                            left: Box::new(left),
                            right: Box::new(right),
                        },
                        new_sp,
                    ),
                );
            } else {
                i += 1;
            }
        }
    }
    operands
        .into_iter()
        .next()
        .unwrap_or_else(|| Spanned::new(Expr::Literal(Literal::Int(0)), Span::new(0, 0, file)))
}
fn parse_bin_op(s: &str) -> BinOp {
    match s {
        "+" => BinOp::Add,
        "-" => BinOp::Sub,
        "*" => BinOp::Mul,
        "/" => BinOp::Div,
        "==" => BinOp::Eq,
        "!=" => BinOp::Neq,
        "<" => BinOp::Lt,
        ">" => BinOp::Gt,
        "<=" => BinOp::Lte,
        ">=" => BinOp::Gte,
        "&&" => BinOp::And,
        "||" => BinOp::Or,
        ".." => BinOp::Range,
        _ => BinOp::Add,
    }
}
