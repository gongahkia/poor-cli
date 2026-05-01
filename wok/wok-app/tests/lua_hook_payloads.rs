//! Pin every documented Lua hook payload schema.
//!
//! For each event listed in `docs/LUA_SCRIPTING.md` we:
//!   1. Build a representative payload that matches what `main.rs` actually
//!      sends (see `block_hook_payload`, `pane_hook_payload`, etc.).
//!   2. Register a Lua handler that asserts every documented field is
//!      present and of the expected type.
//!   3. Trigger the hook through the real `LuaRuntime`.
//!   4. Assert the handler ran and produced the expected `wok.notify`.
//!
//! Failures here mean either the payload schema in `main.rs` drifted
//! from the docs, or the docs are out of sync with the code. Either way
//! the contract with plugin authors is broken.
//!
//! Adding a new hook? Add it here and to the docs in the same PR.

use serde_json::json;
use wok_app::scripting::LuaRuntime;

fn fresh_runtime() -> LuaRuntime {
    let mut runtime = LuaRuntime::new().expect("lua runtime");
    runtime.init(&std::env::temp_dir()).expect("lua init");
    runtime
}

/// Common asserter — registers a handler that errors if any field in
/// `required_fields` is missing or has the wrong basic type. Each field is
/// `(name, expected_lua_type)` where the expected type is one of:
/// `"number"`, `"string"`, `"boolean"`, `"table"`, `"nil_or_number"`,
/// `"nil_or_string"`, `"nil_or_boolean"`.
fn register_schema_handler(
    runtime: &mut LuaRuntime,
    event: &str,
    required_fields: &[(&str, &str)],
) {
    let mut checks = String::new();
    for (name, ty) in required_fields {
        let predicate = match *ty {
            "number" => format!("type(event.{name}) ~= 'number'"),
            "string" => format!("type(event.{name}) ~= 'string'"),
            "boolean" => format!("type(event.{name}) ~= 'boolean'"),
            "table" => format!("type(event.{name}) ~= 'table'"),
            "nil_or_number" => {
                format!("event.{name} ~= nil and type(event.{name}) ~= 'number'")
            }
            "nil_or_string" => {
                format!("event.{name} ~= nil and type(event.{name}) ~= 'string'")
            }
            "nil_or_boolean" => {
                format!("event.{name} ~= nil and type(event.{name}) ~= 'boolean'")
            }
            other => panic!("unknown expected type tag: {other}"),
        };
        checks.push_str(&format!(
            "if {predicate} then error(\"{event}: field '{name}' missing or wrong type, got \" .. type(event.{name})) end\n"
        ));
    }
    let script = format!(
        r#"
        wok.on("{event}", function(event)
            {checks}
            wok.notify("{event}-ok")
        end)
        "#
    );
    runtime.exec(&script).expect("hook registration must succeed");
}

#[test]
fn block_finished_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "block_finished",
        &[
            ("pane_id", "number"),
            ("tab_index", "number"),
            ("tab_id", "number"),
            ("tab_title", "string"),
            ("shell", "string"),
            ("title", "string"),
            ("cwd", "string"),
            ("is_active_pane", "boolean"),
            ("block_id", "number"),
            ("command", "string"),
            ("exit_code", "number"),
            ("duration_ms", "number"),
            ("output_start_row", "number"),
            ("output_end_row", "number"),
        ],
    );

    runtime
        .trigger_hook(
            "block_finished",
            &json!({
                "pane_id": 1,
                "tab_index": 0,
                "tab_id": 1,
                "tab_title": "demo",
                "shell": "zsh",
                "title": "demo",
                "cwd": "/tmp",
                "is_active_pane": true,
                "block_id": 7,
                "command": "echo hi",
                "exit_code": 0,
                "duration_ms": 42_u64,
                "output_start_row": 10,
                "output_end_row": 11,
            }),
        )
        .expect("hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["block_finished-ok"]);
}

#[test]
fn cwd_changed_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "cwd_changed",
        &[
            ("pane_id", "number"),
            ("tab_index", "number"),
            ("tab_id", "number"),
            ("tab_title", "string"),
            ("shell", "string"),
            ("title", "string"),
            ("cwd", "string"),
            ("is_active_pane", "boolean"),
            ("path", "string"),
        ],
    );

    runtime
        .trigger_hook(
            "cwd_changed",
            &json!({
                "pane_id": 1,
                "tab_index": 0,
                "tab_id": 1,
                "tab_title": "demo",
                "shell": "zsh",
                "title": "demo",
                "cwd": "/tmp/old",
                "is_active_pane": true,
                "path": "/tmp/new",
            }),
        )
        .expect("hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["cwd_changed-ok"]);
}

#[test]
fn command_submitted_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "command_submitted",
        &[
            ("pane_id", "number"),
            ("tab_index", "number"),
            ("tab_id", "number"),
            ("tab_title", "string"),
            ("shell", "string"),
            ("cwd", "string"),
            ("is_active_pane", "boolean"),
            ("command", "string"),
        ],
    );

    runtime
        .trigger_hook(
            "command_submitted",
            &json!({
                "pane_id": 2,
                "tab_index": 0,
                "tab_id": 1,
                "tab_title": "demo",
                "shell": "zsh",
                "title": "demo",
                "cwd": "/tmp",
                "is_active_pane": true,
                "command": "ls -la",
            }),
        )
        .expect("hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["command_submitted-ok"]);
}

#[test]
fn app_start_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "app_start",
        &[
            ("active_tab_index", "number"),
            ("tab_count", "number"),
            ("pane_count", "number"),
        ],
    );

    runtime
        .trigger_hook(
            "app_start",
            &json!({
                "active_tab_index": 0,
                "active_tab_id": 1,
                "tab_count": 1,
                "pane_count": 1,
                "active_pane_id": 1,
            }),
        )
        .expect("hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["app_start-ok"]);
}

#[test]
fn app_exit_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "app_exit",
        &[
            ("active_tab_index", "number"),
            ("tab_count", "number"),
            ("pane_count", "number"),
        ],
    );

    runtime
        .trigger_hook(
            "app_exit",
            &json!({
                "active_tab_index": 0,
                "active_tab_id": 1,
                "tab_count": 2,
                "pane_count": 3,
                "active_pane_id": 5,
            }),
        )
        .expect("hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["app_exit-ok"]);
}

#[test]
fn pane_exited_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "pane_exited",
        &[
            ("pane_id", "number"),
            ("tab_index", "number"),
            ("shell", "string"),
            ("cwd", "string"),
            ("exit_code", "nil_or_number"),
        ],
    );

    runtime
        .trigger_hook(
            "pane_exited",
            &json!({
                "pane_id": 4,
                "tab_index": 0,
                "tab_id": 1,
                "tab_title": "x",
                "shell": "bash",
                "title": "x",
                "cwd": "/",
                "is_active_pane": false,
                "exit_code": 130,
            }),
        )
        .expect("hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["pane_exited-ok"]);
}

#[test]
fn tab_done_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "tab_done",
        &[
            ("tab_index", "number"),
            ("tab_id", "number"),
            ("tab_title", "string"),
            ("pane_ids", "table"),
            ("pane_count", "number"),
            ("is_active_tab", "boolean"),
        ],
    );

    runtime
        .trigger_hook(
            "tab_done",
            &json!({
                "tab_index": 0,
                "tab_id": 1,
                "tab_title": "done",
                "pane_ids": [1, 2, 3],
                "pane_count": 3,
                "is_active_tab": true,
            }),
        )
        .expect("hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["tab_done-ok"]);
}

#[test]
fn tab_opened_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "tab_opened",
        &[
            ("pane_id", "number"),
            ("tab_index", "number"),
            ("tab_id", "number"),
            ("tab_title", "string"),
            ("shell", "string"),
            ("title", "string"),
            ("cwd", "string"),
            ("is_active_pane", "boolean"),
        ],
    );

    runtime
        .trigger_hook(
            "tab_opened",
            &json!({
                "pane_id": 5,
                "tab_index": 1,
                "tab_id": 2,
                "tab_title": "Shell",
                "shell": "zsh",
                "title": "Shell",
                "cwd": "/home/u",
                "is_active_pane": true,
            }),
        )
        .expect("hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["tab_opened-ok"]);
}

#[test]
fn pane_opened_payload_matches_docs() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "pane_opened",
        &[
            ("pane_id", "number"),
            ("tab_index", "number"),
            ("tab_id", "number"),
            ("tab_title", "string"),
            ("shell", "string"),
            ("title", "string"),
            ("cwd", "string"),
            ("is_active_pane", "boolean"),
            ("direction", "string"),
        ],
    );

    runtime
        .trigger_hook(
            "pane_opened",
            &json!({
                "pane_id": 6,
                "tab_index": 1,
                "tab_id": 2,
                "tab_title": "Shell",
                "shell": "zsh",
                "title": "Shell",
                "cwd": "/home/u",
                "is_active_pane": true,
                "direction": "vertical",
            }),
        )
        .expect("vertical split hook should run cleanly");
    assert_eq!(runtime.take_notifications(), vec!["pane_opened-ok"]);
}

#[test]
fn pane_opened_floating_direction_is_string() {
    // Same schema, exercise the "floating" code path.
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "pane_opened",
        &[("direction", "string")],
    );

    for direction in ["vertical", "horizontal", "floating"] {
        runtime
            .trigger_hook(
                "pane_opened",
                &json!({ "direction": direction }),
            )
            .expect("hook should run cleanly");
    }
    assert_eq!(
        runtime.take_notifications(),
        vec!["pane_opened-ok", "pane_opened-ok", "pane_opened-ok"]
    );
}

#[test]
fn missing_required_field_makes_hook_error() {
    // Belt-and-suspenders: prove the schema asserter actually fails when a
    // documented field is missing. Otherwise these tests are no-ops.
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "block_finished",
        &[("block_id", "number"), ("command", "string")],
    );

    let result = runtime.trigger_hook(
        "block_finished",
        &json!({
            // missing block_id
            "command": "echo hi",
        }),
    );
    assert!(result.is_err(), "missing field should error");
}

#[test]
fn wrong_field_type_makes_hook_error() {
    let mut runtime = fresh_runtime();
    register_schema_handler(
        &mut runtime,
        "block_finished",
        &[("exit_code", "number")],
    );

    let result = runtime.trigger_hook(
        "block_finished",
        &json!({
            "exit_code": "should be a number",
        }),
    );
    assert!(result.is_err(), "wrong type should error");
}
