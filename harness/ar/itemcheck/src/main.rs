//! G0 item-level allowlist checker (autoresearch evaluator, never run by proposers).
//!
//! Input: a JSON request on stdin (or `--request <file>`):
//!
//! ```json
//! {"allowlist": {"<repo-relative .rs path>": ["const SETTLE_WATCH", "impl FocusSnapshot::fn restore_if_changed_opts"]},
//!  "files": [{"key": "<repo-relative path>", "base": "<file or null>", "cand": "<file or null>",
//!             "hunks": [[base_start, base_len, cand_start, cand_len], ...]}]}
//! ```
//!
//! `hunks` are `git diff -U0` hunk headers for the file. Output: one JSON report
//! (`ar.itemcheck.v1`) on stdout. Exit 0 when the change is inside the allowlist,
//! 1 when any violation was found, 2 on a usage or I/O error.
//!
//! Rules (any violation rejects the candidate):
//! - every item (recursively through inline `mod` and `impl` blocks) whose token
//!   hash differs, appears or disappears must be on the allowlist;
//! - an edited, added or removed `#[test]` / `#[cfg(test)]` item is reported as
//!   its own kind (`test_item_*`), never allowed;
//! - every changed line (from the hunks) must lie inside an allowed item's span,
//!   so comment or blank-line edits between items are rejected too;
//! - the ordered list of `phase_trace` source lines (with their enclosing item)
//!   must be identical, each call's syntactic nesting chain must be unchanged, and
//!   a mark statement must not jump over an unchanged sibling statement;
//! - added or removed `.rs` files are rejected.

use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;

use proc_macro2::{TokenStream, TokenTree};
use quote::ToTokens;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use syn::visit::Visit;

#[derive(Deserialize)]
struct Request {
    allowlist: BTreeMap<String, Vec<String>>,
    files: Vec<FileReq>,
}

#[derive(Deserialize)]
struct FileReq {
    key: String,
    base: Option<String>,
    cand: Option<String>,
    #[serde(default)]
    hunks: Vec<[usize; 4]>,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
struct Violation {
    file: String,
    kind: String,
    item: Option<String>,
    detail: String,
}

#[derive(Clone, Debug)]
struct Item {
    path: String,
    hash: String,
    start: usize,
    end: usize,
    is_test: bool,
}

#[derive(Clone, Debug, PartialEq)]
struct PtCall {
    item: String,
    chain: Vec<&'static str>,
    text: String,
}

#[derive(Clone, Debug, Default)]
struct PtStmt {
    item: String,
    text: String,
    before: BTreeSet<String>,
    after: BTreeSet<String>,
}

#[derive(Default)]
struct Parsed {
    items: Vec<Item>,
    calls: Vec<PtCall>,
    stmts: Vec<PtStmt>,
    lines: Vec<(String, String)>,
}

#[derive(Serialize, Default)]
struct FileReport {
    items_base: usize,
    items_cand: usize,
    phase_trace_lines_base: usize,
    phase_trace_lines_cand: usize,
    changed_allowed: Vec<String>,
    test_items_cand: BTreeMap<String, String>,
}

#[derive(Serialize)]
struct Report {
    schema: &'static str,
    ok: bool,
    violations: Vec<Violation>,
    files: BTreeMap<String, FileReport>,
}

fn sha(text: &str) -> String {
    let mut h = Sha256::new();
    h.update(text.as_bytes());
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

fn line_span(tokens: TokenStream) -> (usize, usize) {
    fn walk(ts: TokenStream, lo: &mut usize, hi: &mut usize) {
        for tt in ts {
            let span = tt.span();
            *lo = (*lo).min(span.start().line);
            *hi = (*hi).max(span.end().line);
            if let TokenTree::Group(g) = tt {
                *lo = (*lo).min(g.span_open().start().line);
                *hi = (*hi).max(g.span_close().end().line);
                walk(g.stream(), lo, hi);
            }
        }
    }
    let (mut lo, mut hi) = (usize::MAX, 0usize);
    walk(tokens, &mut lo, &mut hi);
    (lo, hi)
}

fn attrs_are_test(attrs: &[syn::Attribute]) -> bool {
    attrs.iter().any(|a| {
        let path = a.path();
        let last = path.segments.last().map(|s| s.ident.to_string()).unwrap_or_default();
        if last == "test" {
            return true;
        }
        if path.is_ident("cfg") {
            let text = a.meta.to_token_stream().to_string();
            return text.split(|c: char| !c.is_alphanumeric() && c != '_').any(|w| w == "test");
        }
        false
    })
}

fn path_has_phase_trace(expr: &syn::Expr) -> bool {
    matches!(expr, syn::Expr::Path(p) if p.path.segments.iter().any(|s| s.ident == "phase_trace"))
}

struct PtVisitor<'a> {
    item: String,
    chain: Vec<&'static str>,
    calls: &'a mut Vec<PtCall>,
    stmts: &'a mut Vec<PtStmt>,
}

impl PtVisitor<'_> {
    fn nested(&mut self, kind: &'static str, f: impl FnOnce(&mut Self)) {
        self.chain.push(kind);
        f(self);
        self.chain.pop();
    }
}

fn stmt_is_mark(stmt: &syn::Stmt) -> bool {
    match stmt {
        syn::Stmt::Expr(syn::Expr::Call(c), _) => path_has_phase_trace(&c.func),
        _ => false,
    }
}

impl<'ast> Visit<'ast> for PtVisitor<'_> {
    fn visit_expr_call(&mut self, c: &'ast syn::ExprCall) {
        if path_has_phase_trace(&c.func) {
            self.calls.push(PtCall {
                item: self.item.clone(),
                chain: self.chain.clone(),
                text: c.to_token_stream().to_string(),
            });
        }
        syn::visit::visit_expr_call(self, c);
    }
    fn visit_block(&mut self, b: &'ast syn::Block) {
        let texts: Vec<Option<String>> = b
            .stmts
            .iter()
            .map(|s| (!stmt_is_mark(s)).then(|| s.to_token_stream().to_string()))
            .collect();
        for (i, s) in b.stmts.iter().enumerate() {
            if stmt_is_mark(s) {
                self.stmts.push(PtStmt {
                    item: self.item.clone(),
                    text: s.to_token_stream().to_string(),
                    before: texts[..i].iter().flatten().cloned().collect(),
                    after: texts[i + 1..].iter().flatten().cloned().collect(),
                });
            }
        }
        self.nested("block", |v| syn::visit::visit_block(v, b));
    }
    fn visit_expr_async(&mut self, e: &'ast syn::ExprAsync) {
        self.nested("async", |v| syn::visit::visit_expr_async(v, e));
    }
    fn visit_expr_closure(&mut self, e: &'ast syn::ExprClosure) {
        self.nested("closure", |v| syn::visit::visit_expr_closure(v, e));
    }
    fn visit_expr_if(&mut self, e: &'ast syn::ExprIf) {
        self.nested("if", |v| syn::visit::visit_expr_if(v, e));
    }
    fn visit_expr_loop(&mut self, e: &'ast syn::ExprLoop) {
        self.nested("loop", |v| syn::visit::visit_expr_loop(v, e));
    }
    fn visit_expr_while(&mut self, e: &'ast syn::ExprWhile) {
        self.nested("while", |v| syn::visit::visit_expr_while(v, e));
    }
    fn visit_expr_for_loop(&mut self, e: &'ast syn::ExprForLoop) {
        self.nested("for", |v| syn::visit::visit_expr_for_loop(v, e));
    }
    fn visit_arm(&mut self, a: &'ast syn::Arm) {
        self.nested("arm", |v| syn::visit::visit_arm(v, a));
    }
    fn visit_expr_unsafe(&mut self, e: &'ast syn::ExprUnsafe) {
        self.nested("unsafe", |v| syn::visit::visit_expr_unsafe(v, e));
    }
}

struct Collector {
    out: Parsed,
    seen: BTreeMap<String, usize>,
}

impl Collector {
    fn unique(&mut self, path: String) -> String {
        let n = self.seen.entry(path.clone()).or_insert(0);
        *n += 1;
        if *n == 1 {
            path
        } else {
            format!("{path}#{n}")
        }
    }

    fn push(&mut self, path: String, tokens: TokenStream, is_test: bool) -> String {
        let path = self.unique(path);
        let (start, end) = line_span(tokens.clone());
        self.out.items.push(Item {
            path: path.clone(),
            hash: sha(&tokens.to_string()),
            start,
            end,
            is_test,
        });
        path
    }

    fn visit_fn_body(&mut self, item: &str, f: impl FnOnce(&mut PtVisitor)) {
        let mut v = PtVisitor {
            item: item.to_owned(),
            chain: Vec::new(),
            calls: &mut self.out.calls,
            stmts: &mut self.out.stmts,
        };
        f(&mut v);
    }

    fn items(&mut self, items: &[syn::Item], prefix: &str, in_test: bool) {
        for item in items {
            self.item(item, prefix, in_test);
        }
    }

    fn item(&mut self, item: &syn::Item, prefix: &str, in_test: bool) {
        use syn::Item as I;
        let tokens = item.to_token_stream();
        let name = |kind: &str, ident: &syn::Ident| format!("{prefix}{kind} {ident}");
        match item {
            I::Fn(f) => {
                let t = in_test || attrs_are_test(&f.attrs);
                let path = self.push(name("fn", &f.sig.ident), tokens, t);
                self.visit_fn_body(&path, |v| v.visit_item_fn(f));
            }
            I::Const(c) => {
                let t = in_test || attrs_are_test(&c.attrs);
                let path = self.push(name("const", &c.ident), tokens, t);
                self.visit_fn_body(&path, |v| v.visit_item_const(c));
            }
            I::Static(s) => {
                let t = in_test || attrs_are_test(&s.attrs);
                let path = self.push(name("static", &s.ident), tokens, t);
                self.visit_fn_body(&path, |v| v.visit_item_static(s));
            }
            I::Struct(s) => {
                let t = in_test || attrs_are_test(&s.attrs);
                self.push(name("struct", &s.ident), tokens, t);
            }
            I::Enum(e) => {
                let t = in_test || attrs_are_test(&e.attrs);
                self.push(name("enum", &e.ident), tokens, t);
            }
            I::Union(u) => {
                let t = in_test || attrs_are_test(&u.attrs);
                self.push(name("union", &u.ident), tokens, t);
            }
            I::Type(ty) => {
                let t = in_test || attrs_are_test(&ty.attrs);
                self.push(name("type", &ty.ident), tokens, t);
            }
            I::Trait(tr) => {
                let t = in_test || attrs_are_test(&tr.attrs);
                let path = self.push(name("trait", &tr.ident), tokens, t);
                self.visit_fn_body(&path, |v| v.visit_item_trait(tr));
            }
            I::TraitAlias(tr) => {
                let t = in_test || attrs_are_test(&tr.attrs);
                self.push(name("trait", &tr.ident), tokens, t);
            }
            I::Use(u) => {
                let t = in_test || attrs_are_test(&u.attrs);
                let text = u.tree.to_token_stream().to_string();
                self.push(format!("{prefix}use {text}"), tokens, t);
            }
            I::ExternCrate(e) => {
                let t = in_test || attrs_are_test(&e.attrs);
                self.push(name("extern crate", &e.ident), tokens, t);
            }
            I::Macro(m) => {
                let t = in_test || attrs_are_test(&m.attrs);
                let label = match &m.ident {
                    Some(ident) => format!("{prefix}macro_rules {ident}"),
                    None => format!("{prefix}macro {}!", m.mac.path.to_token_stream()),
                };
                self.push(label, tokens, t);
            }
            I::Mod(m) => {
                let t = in_test || attrs_are_test(&m.attrs);
                // The mod item itself carries its attributes and name; nested items
                // are their own entries (the smallest containing span wins below).
                let header = {
                    let mut h = TokenStream::new();
                    for a in &m.attrs {
                        a.to_tokens(&mut h);
                    }
                    m.vis.to_tokens(&mut h);
                    m.ident.to_tokens(&mut h);
                    h
                };
                let path = self.unique(name("mod", &m.ident));
                let (start, end) = line_span(tokens);
                self.out.items.push(Item {
                    path: path.clone(),
                    hash: sha(&header.to_string()),
                    start,
                    end,
                    is_test: t,
                });
                if let Some((_, inner)) = &m.content {
                    self.items(inner, &format!("{path}::"), t);
                }
            }
            I::Impl(i) => {
                let t = in_test || attrs_are_test(&i.attrs);
                let mut label = String::from("impl ");
                if let Some((bang, trait_path, _)) = &i.trait_ {
                    if bang.is_some() {
                        label.push('!');
                    }
                    label.push_str(&trait_path.to_token_stream().to_string());
                    label.push_str(" for ");
                }
                label.push_str(&i.self_ty.to_token_stream().to_string());
                let header = {
                    let mut h = TokenStream::new();
                    for a in &i.attrs {
                        a.to_tokens(&mut h);
                    }
                    i.generics.to_tokens(&mut h);
                    i.generics.where_clause.to_tokens(&mut h);
                    h.extend(label.parse::<TokenStream>().unwrap_or_default());
                    h
                };
                let impl_path = self.unique(format!("{prefix}{label}"));
                let (start, end) = line_span(tokens);
                self.out.items.push(Item {
                    path: impl_path.clone(),
                    hash: sha(&header.to_string()),
                    start,
                    end,
                    is_test: t,
                });
                for ii in &i.items {
                    use syn::ImplItem as II;
                    let it = ii.to_token_stream();
                    match ii {
                        II::Fn(f) => {
                            let tt = t || attrs_are_test(&f.attrs);
                            let path = self.push(format!("{impl_path}::fn {}", f.sig.ident), it, tt);
                            self.visit_fn_body(&path, |v| v.visit_impl_item_fn(f));
                        }
                        II::Const(c) => {
                            let tt = t || attrs_are_test(&c.attrs);
                            self.push(format!("{impl_path}::const {}", c.ident), it, tt);
                        }
                        II::Type(ty) => {
                            let tt = t || attrs_are_test(&ty.attrs);
                            self.push(format!("{impl_path}::type {}", ty.ident), it, tt);
                        }
                        II::Macro(m) => {
                            let tt = t || attrs_are_test(&m.attrs);
                            self.push(format!("{impl_path}::macro {}!", m.mac.path.to_token_stream()), it, tt);
                        }
                        _ => {
                            self.push(format!("{impl_path}::verbatim"), it, t);
                        }
                    }
                }
            }
            I::ForeignMod(_) => {
                self.push(format!("{prefix}extern block"), tokens, in_test);
            }
            _ => {
                self.push(format!("{prefix}verbatim"), tokens, in_test);
            }
        }
    }
}

fn parse(src: &str) -> Result<Parsed, String> {
    let file = syn::parse_file(src).map_err(|e| format!("{e} at {:?}", e.span().start()))?;
    let mut c = Collector {
        out: Parsed::default(),
        seen: BTreeMap::new(),
    };
    c.items(&file.items, "", false);
    // Text-level phase_trace lines with their innermost enclosing item (catches
    // marks inside macro invocations, which syn does not parse).
    let mut lines = Vec::new();
    for (i, line) in src.lines().enumerate() {
        if line.contains("phase_trace") {
            let item = innermost(&c.out.items, i + 1)
                .map(|it| it.path.clone())
                .unwrap_or_else(|| "<between items>".into());
            lines.push((item, line.trim().to_owned()));
        }
    }
    c.out.lines = lines;
    Ok(c.out)
}

fn innermost(items: &[Item], line: usize) -> Option<&Item> {
    items
        .iter()
        .filter(|it| it.start <= line && line <= it.end)
        .min_by_key(|it| it.end - it.start)
}

fn check_file(
    key: &str,
    base: Option<&str>,
    cand: Option<&str>,
    hunks: &[[usize; 4]],
    allowed: &BTreeSet<String>,
    report: &mut FileReport,
) -> Vec<Violation> {
    let v = |kind: &str, item: Option<String>, detail: String| Violation {
        file: key.to_owned(),
        kind: kind.to_owned(),
        item,
        detail,
    };
    let (base_src, cand_src) = match (base, cand) {
        (Some(b), Some(c)) => (b, c),
        (None, Some(_)) => return vec![v("file_added", None, "new .rs file".into())],
        (Some(_), None) => return vec![v("file_removed", None, "deleted .rs file".into())],
        (None, None) => return vec![],
    };
    let b = match parse(base_src) {
        Ok(p) => p,
        Err(e) => return vec![v("parse_error_base", None, e)],
    };
    let c = match parse(cand_src) {
        Ok(p) => p,
        Err(e) => return vec![v("parse_error_cand", None, e)],
    };
    let mut out = Vec::new();
    report.items_base = b.items.len();
    report.items_cand = c.items.len();
    report.phase_trace_lines_base = b.lines.len();
    report.phase_trace_lines_cand = c.lines.len();
    for it in c.items.iter().filter(|it| it.is_test) {
        report.test_items_cand.insert(it.path.clone(), it.hash.clone());
    }

    // 1. Item hashes.
    let bm: BTreeMap<&str, &Item> = b.items.iter().map(|i| (i.path.as_str(), i)).collect();
    let cm: BTreeMap<&str, &Item> = c.items.iter().map(|i| (i.path.as_str(), i)).collect();
    let keys: BTreeSet<&str> = bm.keys().chain(cm.keys()).copied().collect();
    for k in keys {
        match (bm.get(k), cm.get(k)) {
            (Some(x), Some(y)) if x.hash == y.hash => {}
            (Some(x), Some(_)) => {
                if x.is_test {
                    out.push(v("test_item_changed", Some(k.into()), "test item edited".into()));
                } else if allowed.contains(k) {
                    report.changed_allowed.push(k.to_owned());
                } else {
                    out.push(v("item_changed_not_allowed", Some(k.into()), "item outside the segment allowlist".into()));
                }
            }
            (Some(x), None) => {
                let kind = if x.is_test { "test_item_removed" } else { "item_removed" };
                out.push(v(kind, Some(k.into()), "item removed or renamed".into()));
            }
            (None, Some(y)) => {
                let kind = if y.is_test { "test_item_added" } else { "item_added" };
                out.push(v(kind, Some(k.into()), "new item".into()));
            }
            (None, None) => {}
        }
    }

    // 2. Every changed line inside an allowed item.
    let mut line_check = |items: &[Item], start: usize, len: usize, side: &str| {
        for line in start..start + len {
            match innermost(items, line) {
                Some(it) if allowed.contains(&it.path) => {}
                Some(it) => out.push(v(
                    if it.is_test { "test_item_changed" } else { "line_outside_allowed_item" },
                    Some(it.path.clone()),
                    format!("{side} line {line}"),
                )),
                None => out.push(v("line_outside_allowed_item", None, format!("{side} line {line} (between items)"))),
            }
        }
    };
    for h in hunks {
        let [bs, bl, cs, cl] = *h;
        line_check(&b.items, bs, bl, "base");
        line_check(&c.items, cs, cl, "cand");
    }

    // 3. phase_trace lines: same ordered (item, text) list, same nesting chains,
    //    no jump over an unchanged sibling statement.
    if b.lines != c.lines {
        let detail = format!(
            "phase_trace lines differ (base {} vs cand {}): first difference at index {}",
            b.lines.len(),
            c.lines.len(),
            b.lines.iter().zip(&c.lines).take_while(|(x, y)| x == y).count()
        );
        out.push(v("phase_trace_changed", None, detail));
    } else if b.calls != c.calls {
        let at = b.calls.iter().zip(&c.calls).take_while(|(x, y)| x == y).count();
        let item = c.calls.get(at).or(b.calls.get(at)).map(|x| x.item.clone());
        out.push(v("phase_trace_moved", item, format!("nesting chain changed at call {at}")));
    } else if b.stmts.len() == c.stmts.len() {
        for (x, y) in b.stmts.iter().zip(&c.stmts) {
            let jumped_back = y.before.iter().any(|s| x.after.contains(s) && !x.before.contains(s));
            let jumped_fwd = y.after.iter().any(|s| x.before.contains(s) && !x.after.contains(s));
            if x.text != y.text || jumped_back || jumped_fwd {
                out.push(v("phase_trace_moved", Some(y.item.clone()), format!("mark moved past a sibling: {}", y.text)));
            }
        }
    } else {
        out.push(v("phase_trace_moved", None, "mark statement count changed".into()));
    }
    out
}

fn run(req: Request) -> Result<Report, String> {
    let mut violations = Vec::new();
    let mut files = BTreeMap::new();
    for f in &req.files {
        if !f.key.ends_with(".rs") {
            violations.push(Violation {
                file: f.key.clone(),
                kind: "not_rust".into(),
                item: None,
                detail: "itemcheck only accepts .rs files".into(),
            });
            continue;
        }
        let read = |p: &Option<String>| -> Result<Option<String>, String> {
            p.as_ref()
                .map(|p| std::fs::read_to_string(p).map_err(|e| format!("{p}: {e}")))
                .transpose()
        };
        let base = read(&f.base)?;
        let cand = read(&f.cand)?;
        let allowed: BTreeSet<String> = req.allowlist.get(&f.key).cloned().unwrap_or_default().into_iter().collect();
        let mut fr = FileReport::default();
        violations.extend(check_file(&f.key, base.as_deref(), cand.as_deref(), &f.hunks, &allowed, &mut fr));
        files.insert(f.key.clone(), fr);
    }
    Ok(Report {
        schema: "ar.itemcheck.v1",
        ok: violations.is_empty(),
        violations,
        files,
    })
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut text = String::new();
    let res = match args.get(1).map(String::as_str) {
        Some("--request") => args
            .get(2)
            .ok_or_else(|| "missing file".to_string())
            .and_then(|p| std::fs::read_to_string(p).map_err(|e| e.to_string())),
        Some("--items") => {
            // Debug aid: list the items of one file with spans.
            let src = std::fs::read_to_string(args.get(2).expect("file")).expect("read");
            match parse(&src) {
                Ok(p) => {
                    for it in p.items {
                        println!("{}-{}\t{}\t{}", it.start, it.end, if it.is_test { "T" } else { "-" }, it.path);
                    }
                    std::process::exit(0);
                }
                Err(e) => {
                    eprintln!("{e}");
                    std::process::exit(2);
                }
            }
        }
        _ => std::io::stdin().read_to_string(&mut text).map(|_| text).map_err(|e| e.to_string()),
    };
    let report = res
        .and_then(|t| serde_json::from_str::<Request>(&t).map_err(|e| e.to_string()))
        .and_then(run);
    match report {
        Ok(r) => {
            println!("{}", serde_json::to_string_pretty(&r).unwrap());
            std::process::exit(if r.ok { 0 } else { 1 });
        }
        Err(e) => {
            eprintln!("itemcheck: {e}");
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const BASE: &str = r#"
use std::time::Duration;

/// Watch.
const SETTLE_WATCH: Duration = Duration::from_millis(220);
const OTHER: u32 = 1;

struct S;

impl S {
    fn poll(&self) {
        cua_driver_core::phase_trace::mark("g", "a");
        std::thread::sleep(SETTLE_WATCH);
        let x = 1;
        cua_driver_core::phase_trace::mark("g", "b");
    }
    fn other(&self) {}
}

#[cfg(test)]
mod tests {
    #[test]
    fn t() { assert_eq!(1, 1); }
}
"#;

    fn allow() -> BTreeSet<String> {
        ["const SETTLE_WATCH", "impl S::fn poll"].iter().map(|s| s.to_string()).collect()
    }

    fn kinds(cand: &str, hunks: &[[usize; 4]]) -> Vec<String> {
        let mut fr = FileReport::default();
        check_file("f.rs", Some(BASE), Some(cand), hunks, &allow(), &mut fr)
            .into_iter()
            .map(|v| v.kind)
            .collect()
    }

    #[test]
    fn identical_is_clean() {
        assert!(kinds(BASE, &[]).is_empty());
    }

    #[test]
    fn allowed_const_edit_passes() {
        let cand = BASE.replace("from_millis(220)", "from_millis(120)");
        assert!(kinds(&cand, &[[5, 1, 5, 1]]).is_empty());
    }

    #[test]
    fn allowed_fn_edit_passes() {
        let cand = BASE.replace("let x = 1;", "let x = 2;");
        assert!(kinds(&cand, &[[14, 1, 14, 1]]).is_empty());
    }

    #[test]
    fn removing_sleep_between_marks_passes() {
        let cand = BASE.replace("        std::thread::sleep(SETTLE_WATCH);\n", "");
        assert!(kinds(&cand, &[[13, 1, 12, 0]]).is_empty());
    }

    #[test]
    fn disallowed_item_edit_fails() {
        let cand = BASE.replace("const OTHER: u32 = 1;", "const OTHER: u32 = 2;");
        assert!(kinds(&cand, &[[6, 1, 6, 1]]).contains(&"item_changed_not_allowed".to_string()));
    }

    #[test]
    fn test_item_edit_fails() {
        let cand = BASE.replace("assert_eq!(1, 1)", "assert_eq!(2, 2)");
        assert!(kinds(&cand, &[[23, 1, 23, 1]]).contains(&"test_item_changed".to_string()));
    }

    #[test]
    fn added_item_fails() {
        let cand = BASE.replace("struct S;", "struct S;\nfn helper() {}");
        assert!(kinds(&cand, &[[8, 0, 9, 1]]).contains(&"item_added".to_string()));
    }

    #[test]
    fn comment_between_items_fails() {
        let cand = BASE.replace("struct S;", "// note\nstruct S;");
        assert!(kinds(&cand, &[[7, 0, 8, 1]]).contains(&"line_outside_allowed_item".to_string()));
    }

    #[test]
    fn removed_phase_trace_line_fails() {
        let cand = BASE.replace("        cua_driver_core::phase_trace::mark(\"g\", \"b\");\n", "");
        assert!(kinds(&cand, &[[15, 1, 14, 0]]).contains(&"phase_trace_changed".to_string()));
    }

    #[test]
    fn added_phase_trace_line_fails() {
        let cand = BASE.replace("let x = 1;", "let x = 1;\n        cua_driver_core::phase_trace::mark(\"g\", \"c\");");
        assert!(kinds(&cand, &[[14, 0, 15, 1]]).contains(&"phase_trace_changed".to_string()));
    }

    #[test]
    fn mark_moved_past_unchanged_sibling_fails() {
        let cand = BASE.replace(
            "        cua_driver_core::phase_trace::mark(\"g\", \"a\");\n        std::thread::sleep(SETTLE_WATCH);\n",
            "        std::thread::sleep(SETTLE_WATCH);\n        cua_driver_core::phase_trace::mark(\"g\", \"a\");\n",
        );
        assert!(kinds(&cand, &[[12, 2, 12, 2]]).contains(&"phase_trace_moved".to_string()));
    }

    #[test]
    fn mark_moved_into_nested_block_fails() {
        let cand = BASE.replace(
            "        cua_driver_core::phase_trace::mark(\"g\", \"b\");\n",
            "        if x > 0 { cua_driver_core::phase_trace::mark(\"g\", \"b\"); }\n",
        );
        let k = kinds(&cand, &[[15, 1, 15, 1]]);
        assert!(k.iter().any(|k| k.starts_with("phase_trace")), "{k:?}");
    }

    #[test]
    fn added_file_fails() {
        let mut fr = FileReport::default();
        let v = check_file("n.rs", None, Some("fn a() {}"), &[], &allow(), &mut fr);
        assert_eq!(v[0].kind, "file_added");
    }

    #[test]
    fn cfg_variants_get_distinct_paths() {
        let p = parse("#[cfg(unix)] fn a() {}\n#[cfg(not(unix))] fn a() {}\n").unwrap();
        let paths: Vec<_> = p.items.iter().map(|i| i.path.clone()).collect();
        assert_eq!(paths, vec!["fn a", "fn a#2"]);
    }
}
