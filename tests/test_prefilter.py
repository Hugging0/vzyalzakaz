from app.schemas import RawOpportunity
from app.services.prefilter import evaluate


def test_good_project_passes(profile):
    raw = RawOpportunity(
        source="test",
        source_type="telegram",
        external_id="1",
        title="Python FastAPI automation project",
        raw_text="Нужен Telegram bot, REST API, PostgreSQL. Удалённо, фриланс.",
        remote=True,
    )
    result = evaluate(raw, profile)
    assert result.passed
    assert result.score >= 50


def test_office_job_is_rejected(profile):
    raw = RawOpportunity(
        source="test",
        source_type="telegram",
        external_id="2",
        title="Python developer",
        raw_text="Полная занятость, только офис, 40 часов в неделю.",
    )
    result = evaluate(raw, profile)
    assert not result.passed
    assert "office" in result.negative_matches


def test_full_time_only_is_rejected_but_contract_option_can_pass(profile):
    full_time = RawOpportunity(
        source="test",
        source_type="web",
        external_id="ft",
        title="Python AI engineer",
        raw_text="Remote full time Python AI automation role",
    )
    flexible = full_time.model_copy(
        update={"external_id": "contract", "raw_text": "Remote full time or contract Python AI automation"}
    )
    assert not evaluate(full_time, profile).passed
    assert evaluate(flexible, profile).passed


def test_farsi_project_passes(profile):
    raw = RawOpportunity(
        source="test",
        source_type="telegram",
        external_id="3",
        raw_text="پروژه فریلنس پایتون و ربات تلگرام، دورکاری",
        remote=True,
    )
    assert evaluate(raw, profile).passed


def test_candidate_resume_is_rejected(profile):
    raw = RawOpportunity(
        source="hackernews",
        source_type="web",
        external_id="candidate-1",
        title="Location: Berlin — Python developer",
        raw_text="Remote: Yes. Willing to relocate: Yes. Python, FastAPI.",
    )

    result = evaluate(raw, profile)

    assert not result.passed
    assert "candidate_profile" in result.negative_matches


def test_hybrid_role_is_rejected_for_remote_profile(profile):
    raw = RawOpportunity(
        source="hackernews",
        source_type="web",
        external_id="hybrid-1",
        title="Python engineer — hybrid",
        raw_text="Python backend role, three days per week in-office.",
    )

    result = evaluate(raw, profile)

    assert not result.passed
    assert "office" in result.negative_matches
