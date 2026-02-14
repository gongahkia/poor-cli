use std::collections::HashMap;
use chrono::NaiveDate;

use crate::lang::ast::*;
use crate::model::types::*;
use crate::model::world::World;
use super::env::Environment;
use super::builtins;

const MAX_STACK_DEPTH: usize = 256;

/// Runtime error (Task 37)
#[derive(Debug)]
pub struct RuntimeError {
    pub message: String,
    pub span: Option<Span>,
}

impl std::fmt::Display for RuntimeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if let Some(sp) = &self.span {
            write!(f, "[{}:{}..{}] {}", sp.file, sp.start, sp.end, self.message)
        } else {
            write!(f, "{}", self.message)
        }
    }
}

pub struct Evaluator {
    pub world: World,
    pub env: Environment,
    stack_depth: usize,
}

impl Evaluator {
    pub fn new() -> Self {
        Self {
            world: World::new(),
            env: Environment::new(),
            stack_depth: 0,
        }
    }

    pub fn eval_program(&mut self, program: &Program) -> Result<(), RuntimeError> {
        for stmt in program {
            self.eval_stmt(stmt)?;
        }
        Ok(())
    }

    fn eval_stmt(&mut self, stmt: &Spanned<Stmt>) -> Result<Value, RuntimeError> {
        match &stmt.node {
            Stmt::TimelineDecl(decl) => self.eval_timeline_decl(decl, &stmt.span),
            Stmt::EntityDecl(decl) => self.eval_entity_decl(decl, &stmt.span),
            Stmt::RelDecl(decl) => self.eval_rel_decl(decl, &stmt.span),
            Stmt::TypeDecl(decl) => self.eval_type_decl(decl),
            Stmt::FnDecl(decl) => self.eval_fn_decl(decl),
            Stmt::LetStmt(decl) => self.eval_let(decl),
            Stmt::Import(_path) => Ok(Value::Null), // handled in module system
            Stmt::If(if_expr) => self.eval_if(if_expr),
            Stmt::Match(match_expr) => self.eval_match(match_expr),
            Stmt::ForLoop(fl) => self.eval_for(fl),
            Stmt::WhileLoop(wl) => self.eval_while(wl),
            Stmt::RepeatLoop(rl) => self.eval_repeat(rl),
            Stmt::ExprStmt(expr) => self.eval_expr(expr),
        }
    }

    /// Timeline construction (Task 32)
    fn eval_timeline_decl(&mut self, decl: &TimelineDecl, span: &Span) -> Result<Value, RuntimeError> {
        let id = self.world.next_id();
        let kind = match decl.kind {
            TimelineKind::Linear => TimelineKindModel::Linear,
            TimelineKind::Branch => TimelineKindModel::Branch,
            TimelineKind::Parallel => TimelineKindModel::Parallel,
            TimelineKind::Loop => TimelineKindModel::Loop,
        };

        let start = if let Some(ref e) = decl.start {
            let val = self.eval_expr(e)?;
            Some(self.value_to_timepoint(&val)?)
        } else { None };
        let end = if let Some(ref e) = decl.end {
            let val = self.eval_expr(e)?;
            Some(self.value_to_timepoint(&val)?)
        } else { None };

        let parent_id = decl.parent.as_ref().and_then(|name| {
            self.world.timeline_by_name(name).map(|t| t.id)
        });

        let fork_point = if let Some((ref tl_name, ref at)) = decl.fork_from {
            let tid = self.world.timeline_by_name(tl_name).map(|t| t.id).unwrap_or(0);
            let val = self.eval_expr(at)?;
            let tp = self.value_to_timepoint(&val)?;
            Some((tid, tp))
        } else { None };

        let merge_point = if let Some((ref tl_name, ref at)) = decl.merge_into {
            let tid = self.world.timeline_by_name(tl_name).map(|t| t.id).unwrap_or(0);
            let val = self.eval_expr(at)?;
            let tp = self.value_to_timepoint(&val)?;
            Some((tid, tp))
        } else { None };

        let loop_config = if let Some(ref count_expr) = decl.loop_count {
            let count = match self.eval_expr(count_expr)? {
                Value::Int(n) => n,
                _ => 1,
            };
            Some(LoopConfig {
                count,
                entry_time: start.clone().unwrap_or(TimePoint::Abstract(0)),
                exit_time: end.clone().unwrap_or(TimePoint::Abstract(count)),
            })
        } else { None };

        let timeline = Timeline {
            id, name: decl.name.clone(), kind, start, end,
            parent_id, fork_point, merge_point, loop_config,
            children: Vec::new(), event_markers: Vec::new(),
        };

        self.world.add_timeline(timeline);
        self.env.bind(decl.name.clone(), Value::Timeline(id));

        // Evaluate body statements
        self.env.push_scope();
        for stmt in &decl.body {
            self.eval_stmt(stmt)?;
        }
        self.env.pop_scope();

        Ok(Value::Timeline(id))
    }

    /// Entity instantiation (Task 33)
    fn eval_entity_decl(&mut self, decl: &EntityDecl, span: &Span) -> Result<Value, RuntimeError> {
        let id = self.world.next_id();
        let type_id = decl.type_ref.clone().unwrap_or_else(|| "entity".to_string());

        let mut attributes = HashMap::new();
        for (name, expr) in &decl.fields {
            let val = self.eval_expr(expr)?;
            attributes.insert(name.clone(), val);
        }

        let mut timeline_appearances = Vec::new();
        for (tl_name, start_expr, end_expr) in &decl.appears_on {
            let tid = self.world.timeline_by_name(tl_name).map(|t| t.id).unwrap_or(0);
            let sv = self.eval_expr(start_expr)?;
            let ev = self.eval_expr(end_expr)?;
            let start = self.value_to_timepoint(&sv)?;
            let end = self.value_to_timepoint(&ev)?;
            timeline_appearances.push((tid, TimeRange { start, end, inclusive_end: true }));
        }

        let entity = Entity {
            id, name: decl.name.clone(), type_id,
            attributes, timeline_appearances,
            lifecycle_events: Vec::new(),
        };

        self.world.add_entity(entity);
        self.env.bind(decl.name.clone(), Value::Entity(id));
        Ok(Value::Entity(id))
    }

    /// Relationship binding (Task 34)
    fn eval_rel_decl(&mut self, decl: &RelDecl, span: &Span) -> Result<Value, RuntimeError> {
        let source_id = self.resolve_entity_id(&decl.source)
            .ok_or_else(|| RuntimeError {
                message: format!("undefined entity: {}", decl.source),
                span: Some(span.clone()),
            })?;
        let target_id = self.resolve_entity_id(&decl.target)
            .ok_or_else(|| RuntimeError {
                message: format!("undefined entity: {}", decl.target),
                span: Some(span.clone()),
            })?;

        let temporal_scope = if let Some((ref s, ref e)) = decl.temporal_scope {
            let sv = self.eval_expr(s)?;
            let ev = self.eval_expr(e)?;
            let start = self.value_to_timepoint(&sv)?;
            let end = self.value_to_timepoint(&ev)?;
            Some(TimeRange { start, end, inclusive_end: true })
        } else { None };

        let id = self.world.next_id();
        let rel = Relationship {
            id,
            source_entity_id: source_id,
            target_entity_id: target_id,
            label: decl.label.clone().unwrap_or_default(),
            directed: decl.directed,
            temporal_scope,
            attributes: HashMap::new(),
        };

        self.world.add_relationship(rel);
        Ok(Value::Null)
    }

    fn eval_type_decl(&mut self, decl: &TypeDecl) -> Result<Value, RuntimeError> {
        let mut meta = HashMap::new();
        for (k, v) in &decl.meta {
            let val = self.eval_expr(v)?;
            meta.insert(k.clone(), val);
        }

        let typedef = TypeDef {
            name: decl.name.clone(),
            parent: decl.parent.clone(),
            fields: decl.fields.iter().map(|f| TypeFieldDef {
                name: f.name.clone(),
                type_name: f.type_ann.clone(),
                optional: f.optional,
            }).collect(),
            meta,
        };
        self.world.add_type(typedef);
        Ok(Value::Null)
    }

    fn eval_fn_decl(&mut self, decl: &FnDecl) -> Result<Value, RuntimeError> {
        let fndef = FnDef {
            name: decl.name.clone(),
            params: decl.params.iter().map(|p| (p.name.clone(), p.type_ann.clone())).collect(),
            return_type: decl.return_type.clone(),
            body: decl.body.clone(),
        };
        self.world.add_fn(fndef);
        Ok(Value::Null)
    }

    /// Let binding (Task 8 eval)
    fn eval_let(&mut self, decl: &LetStmt) -> Result<Value, RuntimeError> {
        let val = self.eval_expr(&decl.value)?;
        self.env.bind(decl.name.clone(), val);
        Ok(Value::Null)
    }

    /// Conditional evaluation (Task 29)
    fn eval_if(&mut self, if_expr: &IfExpr) -> Result<Value, RuntimeError> {
        let cond = self.eval_expr(&if_expr.condition)?;
        if self.is_truthy(&cond) {
            return self.eval_block(&if_expr.then_block);
        }
        for (cond_expr, block) in &if_expr.else_if_branches {
            let c = self.eval_expr(cond_expr)?;
            if self.is_truthy(&c) {
                return self.eval_block(block);
            }
        }
        if let Some(ref else_block) = if_expr.else_block {
            return self.eval_block(else_block);
        }
        Ok(Value::Null)
    }

    fn eval_match(&mut self, match_expr: &MatchExpr) -> Result<Value, RuntimeError> {
        let subject = self.eval_expr(&match_expr.subject)?;
        for arm in &match_expr.arms {
            if self.pattern_matches(&arm.pattern.node, &subject) {
                return self.eval_block(&arm.body);
            }
        }
        Ok(Value::Null)
    }

    /// Loop evaluation (Task 30)
    fn eval_for(&mut self, fl: &ForLoop) -> Result<Value, RuntimeError> {
        let iterable = self.eval_expr(&fl.iterable)?;
        let items = match iterable {
            Value::List(items) => items,
            Value::Int(n) => (0..n).map(Value::Int).collect(),
            _ => Vec::new(),
        };

        self.env.push_scope();
        let mut last = Value::Null;
        for item in items {
            self.env.bind(fl.var.clone(), item);
            last = self.eval_block(&fl.body)?;
        }
        self.env.pop_scope();
        Ok(last)
    }

    fn eval_while(&mut self, wl: &WhileLoop) -> Result<Value, RuntimeError> {
        self.env.push_scope();
        let mut last = Value::Null;
        let mut iterations = 0;
        loop {
            let cond = self.eval_expr(&wl.condition)?;
            if !self.is_truthy(&cond) { break; }
            last = self.eval_block(&wl.body)?;
            iterations += 1;
            if iterations > 10000 {
                return Err(RuntimeError {
                    message: "while loop exceeded 10000 iterations".into(),
                    span: None,
                });
            }
        }
        self.env.pop_scope();
        Ok(last)
    }

    fn eval_repeat(&mut self, rl: &RepeatLoop) -> Result<Value, RuntimeError> {
        let count = match self.eval_expr(&rl.count)? {
            Value::Int(n) => n,
            _ => 0,
        };
        self.env.push_scope();
        let mut last = Value::Null;
        for _ in 0..count {
            last = self.eval_block(&rl.body)?;
        }
        self.env.pop_scope();
        Ok(last)
    }

    fn eval_block(&mut self, block: &Block) -> Result<Value, RuntimeError> {
        self.env.push_scope();
        let mut last = Value::Null;
        for stmt in block {
            last = self.eval_stmt(stmt)?;
        }
        self.env.pop_scope();
        Ok(last)
    }

    /// Expression evaluator (Task 28)
    fn eval_expr(&mut self, expr: &Spanned<Expr>) -> Result<Value, RuntimeError> {
        match &expr.node {
            Expr::Literal(lit) => self.eval_literal(lit),
            Expr::Ident(name) => {
                self.env.lookup(name).cloned().ok_or_else(|| RuntimeError {
                    message: format!("undefined variable: {}", name),
                    span: Some(expr.span.clone()),
                })
            }
            Expr::BinOp { op, left, right } => {
                let lv = self.eval_expr(left)?;
                let rv = self.eval_expr(right)?;
                self.eval_binop(op, &lv, &rv, &expr.span)
            }
            Expr::UnaryOp { op, operand } => {
                let v = self.eval_expr(operand)?;
                self.eval_unaryop(op, &v, &expr.span)
            }
            Expr::Call { callee, args } => {
                self.stack_depth += 1;
                if self.stack_depth > MAX_STACK_DEPTH {
                    return Err(RuntimeError {
                        message: "stack overflow".into(),
                        span: Some(expr.span.clone()),
                    });
                }
                let result = self.eval_call(callee, args, &expr.span);
                self.stack_depth -= 1;
                result
            }
            Expr::FieldAccess { object, field } => {
                let obj = self.eval_expr(object)?;
                self.eval_field_access(&obj, field, &expr.span)
            }
            Expr::List(items) => {
                let vals: Result<Vec<_>, _> = items.iter().map(|i| self.eval_expr(i)).collect();
                Ok(Value::List(vals?))
            }
            Expr::Range { start, end } => {
                let s = self.eval_expr(start)?;
                let e = self.eval_expr(end)?;
                match (&s, &e) {
                    (Value::Int(a), Value::Int(b)) => {
                        Ok(Value::List((*a..*b).map(Value::Int).collect()))
                    }
                    _ => Ok(Value::List(vec![s, e]))
                }
            }
            Expr::If(if_expr) => self.eval_if(if_expr),
            Expr::Match(match_expr) => self.eval_match(match_expr),
            Expr::Block(block) => self.eval_block(block),
            Expr::Closure { .. } => Ok(Value::Null), // closures stored but not eval'd here
            Expr::TimeAt { entity, time } => {
                let _t = self.eval_expr(time)?;
                Ok(self.env.lookup(entity).cloned().unwrap_or(Value::Null))
            }
            Expr::Index { object, index } => {
                let obj = self.eval_expr(object)?;
                let idx = self.eval_expr(index)?;
                match (&obj, &idx) {
                    (Value::List(items), Value::Int(i)) => {
                        Ok(items.get(*i as usize).cloned().unwrap_or(Value::Null))
                    }
                    _ => Ok(Value::Null)
                }
            }
        }
    }

    fn eval_literal(&self, lit: &Literal) -> Result<Value, RuntimeError> {
        Ok(match lit {
            Literal::Int(n) => Value::Int(*n),
            Literal::Float(n) => Value::Float(*n),
            Literal::String(s) => Value::String(self.interpolate_string(s)),
            Literal::Bool(b) => Value::Bool(*b),
            Literal::Date(s) => {
                if let Ok(d) = NaiveDate::parse_from_str(s, "%Y-%m-%d") {
                    Value::Date(TimePoint::Absolute(d))
                } else {
                    Value::String(s.clone())
                }
            }
            Literal::Duration(n, unit) => {
                let days = match unit.as_str() {
                    "day" | "days" => *n,
                    "week" | "weeks" => *n * 7,
                    "month" | "months" => *n * 30,
                    "year" | "years" => *n * 365,
                    _ => *n,
                };
                Value::Duration(days)
            }
        })
    }

    fn eval_binop(&self, op: &BinOp, lv: &Value, rv: &Value, span: &Span) -> Result<Value, RuntimeError> {
        match (op, lv, rv) {
            (BinOp::Add, Value::Int(a), Value::Int(b)) => Ok(Value::Int(a + b)),
            (BinOp::Sub, Value::Int(a), Value::Int(b)) => Ok(Value::Int(a - b)),
            (BinOp::Mul, Value::Int(a), Value::Int(b)) => Ok(Value::Int(a * b)),
            (BinOp::Div, Value::Int(a), Value::Int(b)) => {
                if *b == 0 {
                    Err(RuntimeError { message: "division by zero".into(), span: Some(span.clone()) })
                } else {
                    Ok(Value::Int(a / b))
                }
            }
            (BinOp::Add, Value::Float(a), Value::Float(b)) => Ok(Value::Float(a + b)),
            (BinOp::Sub, Value::Float(a), Value::Float(b)) => Ok(Value::Float(a - b)),
            (BinOp::Mul, Value::Float(a), Value::Float(b)) => Ok(Value::Float(a * b)),
            (BinOp::Div, Value::Float(a), Value::Float(b)) => Ok(Value::Float(a / b)),
            (BinOp::Add, Value::String(a), Value::String(b)) => Ok(Value::String(format!("{}{}", a, b))),
            (BinOp::Eq, a, b) => Ok(Value::Bool(self.values_equal(a, b))),
            (BinOp::Neq, a, b) => Ok(Value::Bool(!self.values_equal(a, b))),
            (BinOp::Lt, Value::Int(a), Value::Int(b)) => Ok(Value::Bool(a < b)),
            (BinOp::Gt, Value::Int(a), Value::Int(b)) => Ok(Value::Bool(a > b)),
            (BinOp::Lte, Value::Int(a), Value::Int(b)) => Ok(Value::Bool(a <= b)),
            (BinOp::Gte, Value::Int(a), Value::Int(b)) => Ok(Value::Bool(a >= b)),
            (BinOp::And, Value::Bool(a), Value::Bool(b)) => Ok(Value::Bool(*a && *b)),
            (BinOp::Or, Value::Bool(a), Value::Bool(b)) => Ok(Value::Bool(*a || *b)),
            (BinOp::Range, Value::Int(a), Value::Int(b)) => {
                Ok(Value::List((*a..*b).map(Value::Int).collect()))
            }
            _ => Err(RuntimeError {
                message: format!("type mismatch: cannot apply {:?} to {:?} and {:?}", op, lv, rv),
                span: Some(span.clone()),
            }),
        }
    }

    fn eval_unaryop(&self, op: &UnaryOp, v: &Value, span: &Span) -> Result<Value, RuntimeError> {
        match (op, v) {
            (UnaryOp::Neg, Value::Int(n)) => Ok(Value::Int(-n)),
            (UnaryOp::Neg, Value::Float(n)) => Ok(Value::Float(-n)),
            (UnaryOp::Not, Value::Bool(b)) => Ok(Value::Bool(!b)),
            _ => Err(RuntimeError {
                message: format!("type mismatch: cannot apply {:?} to {:?}", op, v),
                span: Some(span.clone()),
            }),
        }
    }

    /// Function call evaluation (Task 31)
    fn eval_call(&mut self, callee: &Spanned<Expr>, args: &[Spanned<Expr>], span: &Span) -> Result<Value, RuntimeError> {
        let fn_name = match &callee.node {
            Expr::Ident(name) => name.clone(),
            Expr::FieldAccess { object, field } => {
                // method call: evaluate object as first arg
                let obj = self.eval_expr(object)?;
                let mut all_args = vec![obj];
                for a in args {
                    all_args.push(self.eval_expr(a)?);
                }
                if let Some(result) = builtins::register_builtins(&self.world, &all_args, field) {
                    return Ok(result);
                }
                return Err(RuntimeError {
                    message: format!("unknown method: {}", field),
                    span: Some(span.clone()),
                });
            }
            _ => {
                return Err(RuntimeError {
                    message: "not callable".into(),
                    span: Some(span.clone()),
                });
            }
        };

        let mut arg_vals = Vec::new();
        for a in args {
            arg_vals.push(self.eval_expr(a)?);
        }

        // Check builtins first
        if let Some(result) = builtins::register_builtins(&self.world, &arg_vals, &fn_name) {
            return Ok(result);
        }

        // Look up user-defined function
        let fndef = self.world.fn_registry.get(&fn_name).cloned()
            .ok_or_else(|| RuntimeError {
                message: format!("undefined function: {}", fn_name),
                span: Some(span.clone()),
            })?;

        self.env.push_scope();
        for (i, (param_name, _)) in fndef.params.iter().enumerate() {
            let val = arg_vals.get(i).cloned().unwrap_or(Value::Null);
            self.env.bind(param_name.clone(), val);
        }
        let result = self.eval_block(&fndef.body)?;
        self.env.pop_scope();
        Ok(result)
    }

    fn eval_field_access(&self, obj: &Value, field: &str, span: &Span) -> Result<Value, RuntimeError> {
        match obj {
            Value::Entity(id) => {
                if let Some(entity) = self.world.entity_by_id(*id) {
                    match field {
                        "name" => Ok(Value::String(entity.name.clone())),
                        "type" => Ok(Value::String(entity.type_id.clone())),
                        _ => entity.attributes.get(field).cloned().ok_or_else(|| RuntimeError {
                            message: format!("unknown field: {}", field),
                            span: Some(span.clone()),
                        }),
                    }
                } else {
                    Err(RuntimeError { message: format!("entity not found: {}", id), span: Some(span.clone()) })
                }
            }
            Value::Timeline(id) => {
                if let Some(tl) = self.world.timelines.get(id) {
                    match field {
                        "name" => Ok(Value::String(tl.name.clone())),
                        "kind" => Ok(Value::String(format!("{:?}", tl.kind))),
                        _ => Err(RuntimeError { message: format!("unknown timeline field: {}", field), span: Some(span.clone()) })
                    }
                } else {
                    Err(RuntimeError { message: format!("timeline not found: {}", id), span: Some(span.clone()) })
                }
            }
            _ => Err(RuntimeError {
                message: format!("cannot access field '{}' on {:?}", field, obj),
                span: Some(span.clone()),
            }),
        }
    }

    // --- Temporal query evaluator (Task 36) ---

    pub fn entities_at_time(&self, point: &TimePoint) -> Vec<&Entity> {
        self.world.entities.values().filter(|e| {
            e.timeline_appearances.iter().any(|(_, tr)| tr.contains(point))
        }).collect()
    }

    pub fn relationships_at_time(&self, point: &TimePoint) -> Vec<&Relationship> {
        self.world.relationships.iter().filter(|r| {
            r.temporal_scope.as_ref().map_or(true, |ts| ts.contains(point))
        }).collect()
    }

    // --- Helpers ---

    /// String interpolation: replace {var} or {expr.field} with env values (Task 40)
    fn interpolate_string(&self, s: &str) -> String {
        let mut result = String::new();
        let mut chars = s.chars().peekable();

        while let Some(c) = chars.next() {
            if c == '{' {
                let mut expr = String::new();
                let mut depth = 1;
                while let Some(&nc) = chars.peek() {
                    chars.next();
                    if nc == '{' { depth += 1; }
                    if nc == '}' { depth -= 1; if depth == 0 { break; } }
                    expr.push(nc);
                }
                // Try to resolve the expression
                let val = self.resolve_interpolation(&expr);
                result.push_str(&val);
            } else {
                result.push(c);
            }
        }

        result
    }

    fn resolve_interpolation(&self, expr: &str) -> String {
        let parts: Vec<&str> = expr.split('.').collect();
        if parts.is_empty() { return String::new(); }

        // Try simple variable lookup
        if parts.len() == 1 {
            if let Some(val) = self.env.lookup(parts[0]) {
                return format!("{}", val);
            }
        }

        // Try entity.field access
        if parts.len() == 2 {
            let var_name = parts[0];
            let field = parts[1];
            if let Some(Value::Entity(id)) = self.env.lookup(var_name) {
                if let Some(ent) = self.world.entities.get(id) {
                    match field {
                        "name" => return ent.name.clone(),
                        "type" => return ent.type_id.clone(),
                        _ => {
                            if let Some(val) = ent.attributes.get(field) {
                                return format!("{}", val);
                            }
                        }
                    }
                }
            }
        }

        format!("{{{}}}", expr) // Return unresolved
    }

    fn is_truthy(&self, v: &Value) -> bool {
        match v {
            Value::Bool(b) => *b,
            Value::Int(n) => *n != 0,
            Value::Null => false,
            Value::String(s) => !s.is_empty(),
            Value::List(items) => !items.is_empty(),
            _ => true,
        }
    }

    fn values_equal(&self, a: &Value, b: &Value) -> bool {
        match (a, b) {
            (Value::Int(a), Value::Int(b)) => a == b,
            (Value::Float(a), Value::Float(b)) => (a - b).abs() < f64::EPSILON,
            (Value::String(a), Value::String(b)) => a == b,
            (Value::Bool(a), Value::Bool(b)) => a == b,
            (Value::Null, Value::Null) => true,
            _ => false,
        }
    }

    fn pattern_matches(&self, pattern: &Pattern, value: &Value) -> bool {
        match pattern {
            Pattern::Wildcard => true,
            Pattern::Literal(lit) => {
                let lit_val = self.eval_literal(lit).unwrap_or(Value::Null);
                self.values_equal(&lit_val, value)
            }
            Pattern::Ident(_) => true, // bind pattern always matches
        }
    }

    fn resolve_entity_id(&self, name: &str) -> Option<Id> {
        match self.env.lookup(name) {
            Some(Value::Entity(id)) => Some(*id),
            _ => self.world.entity_by_name(name).map(|e| e.id),
        }
    }

    fn value_to_timepoint(&self, val: &Value) -> Result<TimePoint, RuntimeError> {
        match val {
            Value::Date(tp) => Ok(tp.clone()),
            Value::Int(n) => Ok(TimePoint::Abstract(*n)),
            Value::String(s) => {
                if let Ok(d) = NaiveDate::parse_from_str(s, "%Y-%m-%d") {
                    Ok(TimePoint::Absolute(d))
                } else {
                    Ok(TimePoint::EraRef { timeline: String::new(), era: String::new(), point: s.clone() })
                }
            }
            _ => Err(RuntimeError { message: "cannot convert to time point".into(), span: None }),
        }
    }
}
