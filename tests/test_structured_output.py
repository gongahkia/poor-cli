"""tests for poor-cli.structured_output module."""

import unittest

from poor_cli.structured_output import (
    StructuredResponseType,
    StructuredOutputConfig,
    StructuredOutputMetrics,
    EDIT_BLOCK_SCHEMA,
    PLAN_SCHEMA,
    JSON_EDIT_SCHEMA,
    get_schema,
    build_openai_response_format,
    build_gemini_response_schema,
    build_ollama_format,
    should_use_structured_output,
    get_metrics,
    reset_metrics,
)
from poor_cli.providers.tool_translator import ToolTranslator


class TestSchemas(unittest.TestCase):
    def test_edit_block_schema_structure(self):
        s = EDIT_BLOCK_SCHEMA
        self.assertEqual(s["type"], "object")
        self.assertIn("edits", s["properties"])
        items = s["properties"]["edits"]["items"]
        self.assertEqual(set(items["required"]), {"file", "search", "replace"})
        self.assertFalse(items.get("additionalProperties", True))

    def test_plan_schema_structure(self):
        s = PLAN_SCHEMA
        self.assertEqual(s["type"], "object")
        self.assertIn("steps", s["required"])
        step_props = s["properties"]["steps"]["items"]["properties"]
        self.assertIn("description", step_props)

    def test_json_edit_schema_structure(self):
        s = JSON_EDIT_SCHEMA
        self.assertIn("operations", s["required"])
        op_item = s["properties"]["operations"]["items"]
        self.assertIn("op", op_item["required"])
        self.assertIn("path", op_item["required"])

    def test_get_schema_returns_correct(self):
        self.assertIs(get_schema(StructuredResponseType.EDIT_BLOCK), EDIT_BLOCK_SCHEMA)
        self.assertIs(get_schema(StructuredResponseType.PLAN), PLAN_SCHEMA)
        self.assertIs(get_schema(StructuredResponseType.JSON_EDIT), JSON_EDIT_SCHEMA)
        self.assertIsNone(get_schema(StructuredResponseType.TOOL_CALL))


class TestStructuredOutputConfig(unittest.TestCase):
    def test_auto_populates_schema(self):
        cfg = StructuredOutputConfig(response_type=StructuredResponseType.EDIT_BLOCK)
        self.assertEqual(cfg.schema, EDIT_BLOCK_SCHEMA)
        self.assertEqual(cfg.schema_name, "edit_block")

    def test_custom_schema_preserved(self):
        custom = {"type": "object", "properties": {"x": {"type": "string"}}}
        cfg = StructuredOutputConfig(
            response_type=StructuredResponseType.PLAN,
            schema=custom,
            schema_name="custom_plan",
        )
        self.assertEqual(cfg.schema, custom)
        self.assertEqual(cfg.schema_name, "custom_plan")


class TestProviderFormatBuilders(unittest.TestCase):
    def test_openai_response_format(self):
        cfg = StructuredOutputConfig(response_type=StructuredResponseType.EDIT_BLOCK)
        fmt = build_openai_response_format(cfg)
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["json_schema"]["name"], "edit_block")
        self.assertTrue(fmt["json_schema"]["strict"])
        self.assertEqual(fmt["json_schema"]["schema"], EDIT_BLOCK_SCHEMA)

    def test_gemini_response_schema(self):
        cfg = StructuredOutputConfig(response_type=StructuredResponseType.PLAN)
        schema = build_gemini_response_schema(cfg)
        self.assertEqual(schema, PLAN_SCHEMA)

    def test_ollama_format(self):
        cfg = StructuredOutputConfig(response_type=StructuredResponseType.JSON_EDIT)
        self.assertEqual(build_ollama_format(cfg), "json")


class TestShouldUseStructuredOutput(unittest.TestCase):
    def test_returns_false_for_none_type(self):
        self.assertFalse(should_use_structured_output(
            provider_name="openai", supports_structured=True, response_type=None,
        ))

    def test_returns_false_if_unsupported(self):
        self.assertFalse(should_use_structured_output(
            provider_name="openai", supports_structured=False,
            response_type=StructuredResponseType.EDIT_BLOCK,
        ))

    def test_returns_false_for_tool_call(self):
        # tool calls use native function calling, not response_format
        self.assertFalse(should_use_structured_output(
            provider_name="openai", supports_structured=True,
            response_type=StructuredResponseType.TOOL_CALL,
        ))

    def test_returns_true_for_edit_block(self):
        self.assertTrue(should_use_structured_output(
            provider_name="openai", supports_structured=True,
            response_type=StructuredResponseType.EDIT_BLOCK,
        ))

    def test_returns_true_for_plan(self):
        self.assertTrue(should_use_structured_output(
            provider_name="gemini", supports_structured=True,
            response_type=StructuredResponseType.PLAN,
        ))


class TestMetrics(unittest.TestCase):
    def setUp(self):
        reset_metrics()

    def test_structured_success(self):
        m = get_metrics()
        m.record_structured_attempt(success=True)
        m.record_structured_attempt(success=True)
        self.assertEqual(m.structured_requests, 2)
        self.assertEqual(m.structured_successes, 2)
        self.assertAlmostEqual(m.structured_success_rate, 1.0)
        self.assertAlmostEqual(m.fallback_rate, 0.0)

    def test_structured_fallback(self):
        m = get_metrics()
        m.record_structured_attempt(success=True)
        m.record_structured_attempt(success=False)
        self.assertEqual(m.fallback_to_unstructured, 1)
        self.assertAlmostEqual(m.fallback_rate, 0.5)

    def test_unstructured(self):
        m = get_metrics()
        m.record_unstructured()
        m.record_unstructured()
        self.assertEqual(m.total_requests, 2)
        self.assertEqual(m.structured_requests, 0)

    def test_parse_failure_tracking(self):
        m = get_metrics()
        m.record_parse_failure(structured=False)
        m.record_parse_failure(structured=True)
        self.assertEqual(m.parse_failures_before, 1)
        self.assertEqual(m.parse_failures_after, 1)

    def test_summary_keys(self):
        m = get_metrics()
        m.record_structured_attempt(success=True)
        s = m.summary()
        expected_keys = {
            "total_requests", "structured_requests", "structured_successes",
            "fallback_to_unstructured", "structured_success_rate", "fallback_rate",
            "parse_failures_before", "parse_failures_after", "elapsed_seconds",
        }
        self.assertEqual(set(s.keys()), expected_keys)

    def test_zero_division_safe(self):
        m = StructuredOutputMetrics()
        self.assertEqual(m.structured_success_rate, 0.0)
        self.assertEqual(m.fallback_rate, 0.0)


class TestOpenAIStrictTools(unittest.TestCase):
    """Verify tool translator produces strict-mode compatible OpenAI tools."""

    def test_strict_flag_on_tools(self):
        canonical = [{
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "path": {"type": "STRING", "description": "File path"},
                },
                "required": ["path"],
            },
        }]
        result = ToolTranslator.to_openai(canonical)
        self.assertEqual(len(result), 1)
        func = result[0]["function"]
        self.assertTrue(func["strict"])
        params = func["parameters"]
        self.assertFalse(params.get("additionalProperties", True))

    def test_nested_object_gets_additional_properties_false(self):
        canonical = [{
            "name": "edit_file",
            "description": "Edit a file",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "options": {
                        "type": "OBJECT",
                        "properties": {
                            "validate": {"type": "BOOLEAN"},
                        },
                    },
                },
            },
        }]
        result = ToolTranslator.to_openai(canonical)
        inner = result[0]["function"]["parameters"]["properties"]["options"]
        self.assertFalse(inner.get("additionalProperties", True))

    def test_ensure_strict_compatible_adds_required(self):
        """If properties exist but required is missing, it should be auto-populated."""
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "integer"},
            },
        }
        result = ToolTranslator._ensure_strict_compatible(schema)
        self.assertFalse(result["additionalProperties"])
        self.assertIn("required", result)
        self.assertEqual(set(result["required"]), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
