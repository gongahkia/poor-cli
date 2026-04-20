//! JSON-RPC parameter extraction helpers.

use serde_json::Value;

/// Structured JSON-RPC error with standard code.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct RpcError {
    /// JSON-RPC error code.
    pub code: i64,
    /// Human-readable error message.
    pub message: String,
}

impl RpcError {
    /// `-32601` method not found.
    pub fn method_not_found(msg: impl Into<String>) -> Self {
        Self {
            code: -32601,
            message: msg.into(),
        }
    }
    /// `-32602` invalid params.
    pub fn invalid_params(msg: impl Into<String>) -> Self {
        Self {
            code: -32602,
            message: msg.into(),
        }
    }
    /// `-32000` server/runtime error.
    pub fn server_error(msg: impl Into<String>) -> Self {
        Self {
            code: -32000,
            message: msg.into(),
        }
    }
}

impl std::fmt::Display for RpcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{}] {}", self.code, self.message)
    }
}

/// Read one required unsigned integer parameter from array or object forms.
pub(crate) fn jsonrpc_u64_param(params: &Value, index: usize, key: &str) -> Result<u64, String> {
    if let Some(value) = params
        .as_array()
        .and_then(|items| items.get(index))
        .and_then(Value::as_u64)
    {
        return Ok(value);
    }
    if let Some(value) = params.as_object().and_then(|items| items.get(key)) {
        if let Some(value) = value.as_u64() {
            return Ok(value);
        }
    }
    Err(format!("missing or invalid '{key}' parameter"))
}

/// Read one required string parameter from array or object forms.
pub(crate) fn jsonrpc_string_param(
    params: &Value,
    index: usize,
    key: &str,
) -> Result<String, String> {
    if let Some(value) = params
        .as_array()
        .and_then(|items| items.get(index))
        .and_then(Value::as_str)
    {
        return Ok(value.to_string());
    }
    if let Some(value) = params.as_object().and_then(|items| items.get(key)) {
        if let Some(value) = value.as_str() {
            return Ok(value.to_string());
        }
    }
    Err(format!("missing or invalid '{key}' parameter"))
}

/// Read one optional string parameter from array or object forms.
pub(crate) fn jsonrpc_optional_string_param(
    params: &Value,
    index: usize,
    key: &str,
) -> Option<String> {
    params
        .as_array()
        .and_then(|items| items.get(index))
        .and_then(Value::as_str)
        .map(str::to_string)
        .or_else(|| {
            params
                .as_object()
                .and_then(|items| items.get(key))
                .and_then(Value::as_str)
                .map(str::to_string)
        })
}

/// Read one optional unsigned integer parameter from array or object forms.
pub(crate) fn jsonrpc_optional_u64_param(params: &Value, index: usize, key: &str) -> Option<u64> {
    params
        .as_array()
        .and_then(|items| items.get(index))
        .and_then(Value::as_u64)
        .or_else(|| {
            params
                .as_object()
                .and_then(|items| items.get(key))
                .and_then(Value::as_u64)
        })
}

/// Read one optional boolean parameter from array or object forms.
pub(crate) fn jsonrpc_optional_bool_param(params: &Value, index: usize, key: &str) -> Option<bool> {
    params
        .as_array()
        .and_then(|items| items.get(index))
        .and_then(Value::as_bool)
        .or_else(|| {
            params
                .as_object()
                .and_then(|items| items.get(key))
                .and_then(Value::as_bool)
        })
}

/// Read one optional value parameter from array or object forms.
pub(crate) fn jsonrpc_optional_value_param(
    params: &Value,
    index: usize,
    key: &str,
) -> Option<Value> {
    params
        .as_array()
        .and_then(|items| items.get(index))
        .cloned()
        .or_else(|| params.as_object().and_then(|items| items.get(key)).cloned())
}

/// Extract a required u64 pane_id from params with `-32602` on failure.
pub(crate) fn extract_pane_id(params: &Value) -> Result<u64, RpcError> {
    jsonrpc_u64_param(params, 0, "pane_id").map_err(RpcError::invalid_params)
}

/// Extract a row range (start_row, end_row) from params with `-32602` on failure.
pub(crate) fn extract_row_range(params: &Value) -> Result<(usize, usize), RpcError> {
    let start =
        jsonrpc_u64_param(params, 1, "start_row").map_err(RpcError::invalid_params)? as usize;
    let end = jsonrpc_u64_param(params, 2, "end_row").map_err(RpcError::invalid_params)? as usize;
    if start > end {
        return Err(RpcError::invalid_params("start_row must be <= end_row"));
    }
    Ok((start, end))
}

/// Extract an action name and optional params with `-32602` on failure.
pub(crate) fn extract_action_name(params: &Value) -> Result<(String, Option<Value>), RpcError> {
    let name = jsonrpc_string_param(params, 0, "action_name")
        .or_else(|_| jsonrpc_string_param(params, 0, "action"))
        .map_err(RpcError::invalid_params)?;
    let action_params = jsonrpc_optional_value_param(params, 1, "params");
    Ok((name, action_params))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_jsonrpc_string_param_supports_object_and_array() {
        assert_eq!(
            jsonrpc_string_param(&json!(["wok.get_panes"]), 0, "method"),
            Ok("wok.get_panes".to_string())
        );
        assert_eq!(
            jsonrpc_string_param(&json!({"method":"wok.get_panes"}), 0, "method"),
            Ok("wok.get_panes".to_string())
        );
    }

    #[test]
    fn test_extract_pane_id_from_array() {
        assert_eq!(extract_pane_id(&json!([42])), Ok(42));
    }

    #[test]
    fn test_extract_pane_id_from_object() {
        assert_eq!(extract_pane_id(&json!({"pane_id": 7})), Ok(7));
    }

    #[test]
    fn test_extract_pane_id_missing() {
        let err = extract_pane_id(&json!({})).unwrap_err();
        assert_eq!(err.code, -32602);
        let err2 = extract_pane_id(&json!([])).unwrap_err();
        assert_eq!(err2.code, -32602);
    }

    #[test]
    fn test_extract_row_range_valid() {
        assert_eq!(extract_row_range(&json!([0, 5, 10])), Ok((5, 10)));
        assert_eq!(
            extract_row_range(&json!({"pane_id": 0, "start_row": 0, "end_row": 3})),
            Ok((0, 3))
        );
    }

    #[test]
    fn test_extract_row_range_inverted() {
        let err = extract_row_range(&json!([0, 10, 5])).unwrap_err();
        assert_eq!(err.code, -32602);
    }

    #[test]
    fn test_extract_action_name_primary_key() {
        let (name, _) = extract_action_name(&json!(["copy"])).unwrap();
        assert_eq!(name, "copy");
        let (name, _) = extract_action_name(&json!({"action_name": "paste"})).unwrap();
        assert_eq!(name, "paste");
    }

    #[test]
    fn test_extract_action_name_fallback_key() {
        let (name, _) = extract_action_name(&json!({"action": "scroll_up"})).unwrap();
        assert_eq!(name, "scroll_up");
    }

    #[test]
    fn test_extract_action_name_with_params() {
        let (name, params) = extract_action_name(&json!(["focus", {"direction": "up"}])).unwrap();
        assert_eq!(name, "focus");
        assert_eq!(params, Some(json!({"direction": "up"})));
    }

    #[test]
    fn test_extract_action_name_missing() {
        let err = extract_action_name(&json!({})).unwrap_err();
        assert_eq!(err.code, -32602);
    }

    #[test]
    fn test_jsonrpc_optional_value_param_supports_object_and_array() {
        assert_eq!(
            jsonrpc_optional_value_param(&json!([1, {"name":"x"}]), 1, "params"),
            Some(json!({"name":"x"}))
        );
        assert_eq!(
            jsonrpc_optional_value_param(&json!({"params":[1,2,3]}), 0, "params"),
            Some(json!([1, 2, 3]))
        );
    }

    #[test]
    fn test_jsonrpc_optional_u64_param_supports_object_and_array() {
        assert_eq!(
            jsonrpc_optional_u64_param(&json!([1, 2, 3]), 1, "limit"),
            Some(2)
        );
        assert_eq!(
            jsonrpc_optional_u64_param(&json!({"bucket_ms": 60000}), 0, "bucket_ms"),
            Some(60000)
        );
    }

    #[test]
    fn test_jsonrpc_optional_bool_param_supports_object_and_array() {
        assert_eq!(
            jsonrpc_optional_bool_param(&json!([true, false]), 1, "yes"),
            Some(false)
        );
        assert_eq!(
            jsonrpc_optional_bool_param(&json!({"overwrite": true}), 0, "overwrite"),
            Some(true)
        );
    }

    #[test]
    fn test_rpc_error_codes() {
        let e = RpcError::method_not_found("no such method");
        assert_eq!(e.code, -32601);
        assert_eq!(e.message, "no such method");
        let e = RpcError::invalid_params("bad param");
        assert_eq!(e.code, -32602);
        let e = RpcError::server_error("internal");
        assert_eq!(e.code, -32000);
    }

    #[test]
    fn test_rpc_error_display() {
        let e = RpcError::invalid_params("missing 'pane_id'");
        assert_eq!(format!("{e}"), "[-32602] missing 'pane_id'");
    }

    #[test]
    fn test_extract_row_range_missing_param() {
        let err = extract_row_range(&json!({"pane_id": 1})).unwrap_err();
        assert_eq!(err.code, -32602);
        assert!(err.message.contains("start_row"));
    }
}
