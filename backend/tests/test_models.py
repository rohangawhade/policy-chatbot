from adapters.persistence.models import (
    Base,
    Conversation,
    Document,
    DocumentChunk,
    Employee,
    EmployeePolicy,
    Employer,
    Feedback,
    FeedbackRating,
    FlaggedResponse,
    FlaggedResponseStatus,
    GuardrailRejection,
    LLMCostLog,
    Message,
    MessageRole,
    Policy,
    PolicyType,
    RequestLatencyLog,
    UserRole,
)

EXPECTED_TABLES = {
    "employers",
    "employees",
    "policies",
    "employee_policies",
    "documents",
    "document_chunks",
    "conversations",
    "messages",
    "feedback",
    "llm_cost_logs",
    "request_latency_logs",
    "flagged_responses",
    "guardrail_rejections",
}


def test_all_expected_tables_are_registered() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_tenant_scoped_tables_have_an_employer_id_column() -> None:
    tenant_scoped = EXPECTED_TABLES - {"employers", "employee_policies"}
    for table_name in tenant_scoped:
        assert "employer_id" in Base.metadata.tables[table_name].columns


def test_timestamp_mixin_tables_have_created_and_updated_at() -> None:
    for model in (Employer, Employee, Policy, Document, Conversation, FlaggedResponse):
        columns = model.__table__.columns
        assert "created_at" in columns
        assert "updated_at" in columns


def test_enum_members_match_expected_vocabulary() -> None:
    assert {member.value for member in UserRole} == {"admin", "employer", "employee"}
    assert {member.value for member in PolicyType} == {
        "health",
        "dental",
        "vision",
        "life",
        "disability",
    }
    assert {member.value for member in MessageRole} == {"user", "assistant"}
    assert {member.value for member in FeedbackRating} == {"thumbs_up", "thumbs_down"}
    assert {member.value for member in FlaggedResponseStatus} == {
        "pending_review",
        "reviewed",
        "dismissed",
    }


def test_employee_policy_enforces_unique_enrollment_constraint() -> None:
    constraint_names = {c.name for c in EmployeePolicy.__table__.constraints}
    assert "uq_employee_policy" in constraint_names


def test_employee_enforces_unique_email_constraint() -> None:
    constraint_names = {c.name for c in Employee.__table__.constraints}
    assert "uq_employees_email" in constraint_names


def test_relationship_back_populates_are_wired_both_ways() -> None:
    assert Employer.employees.property.back_populates == "employer"
    assert Employee.employer.property.back_populates == "employees"
    assert Document.chunks.property.back_populates == "document"
    assert DocumentChunk.document.property.back_populates == "chunks"
    assert Message.feedback.property.back_populates == "message"
    assert Feedback.message.property.back_populates == "feedback"


def test_domain_analytics_models_expose_required_columns() -> None:
    assert {"model", "model_tier", "estimated_cost_usd"} <= set(LLMCostLog.__table__.columns.keys())
    assert {"total_ms", "retrieval_ms", "llm_ms"} <= set(RequestLatencyLog.__table__.columns.keys())
    assert {"rejection_reason"} <= set(GuardrailRejection.__table__.columns.keys())
