//! JSON-RPC parameter extraction helpers.

use serde_json::Value;

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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_jsonrpc_string_param_supports_object_and_array() {
        assert_eq!(
            jsonrpc_string_param(&json!(["walk.get_panes"]), 0, "method"),
            Ok("walk.get_panes".to_string())
        );
        assert_eq!(
            jsonrpc_string_param(&json!({"method":"walk.get_panes"}), 0, "method"),
            Ok("walk.get_panes".to_string())
        );
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
}
