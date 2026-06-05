"""OpenTelemetry GenAI semantic-convention attribute names (+ Agon extensions).

The ``gen_ai.*`` conventions are still *experimental* (OTel "Development" status), so we pin the
attribute name strings here rather than depend on a fast-moving constants package. Set
``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` in your collector/SDK if it gates them.
"""

# Operation kinds (gen_ai.operation.name values)
OP_CHAT = "chat"
OP_EXECUTE_TOOL = "execute_tool"
OP_INVOKE_AGENT = "invoke_agent"
OP_INVOKE_WORKFLOW = "invoke_workflow"

# gen_ai.* attributes (experimental)
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"

# Agon-specific attributes (grader/scorer spans + run identity)
AGON_RUN_ID = "agon.run_id"
AGON_TASK = "agon.task"
AGON_SCORER = "agon.scorer"
AGON_SCORE_VALUE = "agon.score.value"
AGON_SAMPLE_ID = "agon.sample_id"
