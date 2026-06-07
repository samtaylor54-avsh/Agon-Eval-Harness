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

# Agon eval-outcome attributes (M10 - dashboard enrichment)
AGON_PASSED = "agon.passed"
AGON_COMPOSITE_SCORE = "agon.composite_score"
AGON_CATEGORY = "agon.category"
AGON_RISK_LEVEL = "agon.risk_level"
AGON_ERROR_CATEGORY = "agon.error_category"
AGON_FAILURE_LABELS = "agon.failure_labels"
AGON_OVERALL_PASS_RATE = "agon.overall_pass_rate"
AGON_N_CASES = "agon.n_cases"
AGON_ERROR_COUNT = "agon.error_count"
AGON_ERROR_COUNT_PREFIX = "agon.error_count."  # + <category>
AGON_RECOMMENDATION = "agon.recommendation"
AGON_COST_USD = "agon.cost.usd"
AGON_COST_INPUT_TOKENS = "agon.cost.input_tokens"
AGON_COST_OUTPUT_TOKENS = "agon.cost.output_tokens"
AGON_COST_TOTAL_TOKENS = "agon.cost.total_tokens"
AGON_SYSTEM_VERSION = "agon.system_version"
AGON_DATASET_VERSION = "agon.dataset_version"
