from importlib import import_module

MODULES = (
    "telegram_adapter",
    "application_api",
    "workflow_orchestrator",
    "state_machine",
    "gate_engine",
    "consent_authority",
    "dossier",
    "revision_manager",
    "agent_runtime",
    "context_builder",
    "model_gateway",
    "tool_fact_gateway",
    "evidence_artifact",
    "event_ledger",
    "outbox",
    "scheduler",
    "notifications",
    "cost_usage",
    "observability",
    "health",
    "processes",
)


def test_architecture_component_boundaries_are_importable() -> None:
    for module in MODULES:
        import_module(f"pls.{module}")
