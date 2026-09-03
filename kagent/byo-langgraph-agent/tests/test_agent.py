from agent import _extract_allowed_url, _is_allowed_url, finish, verify_summary
from langchain_core.messages import AIMessage


def test_extract_allowed_url_accepts_prokube():
    assert _extract_allowed_url("Summarize https://prokube.ai please") == (
        "https://prokube.ai"
    )


def test_extract_allowed_url_rejects_other_hosts():
    assert _extract_allowed_url("Summarize https://example.com") is None


def test_allowed_url_rejects_credentials_and_nonstandard_ports():
    assert not _is_allowed_url("https://user@prokube.ai")
    assert not _is_allowed_url("https://prokube.ai:8443")
    assert not _is_allowed_url("https://prokube.ai:invalid")


def test_verify_summary_requires_source_url():
    assert verify_summary(
        {
            "draft": "A sufficiently long summary without the requested source URL.",
            "url": "https://prokube.ai",
        }
    ) == {"summary_valid": False}


def test_finish_appends_missing_source_url():
    result = finish(
        {
            "draft": "prokube helps teams run AI infrastructure.",
            "error": "",
            "url": "https://prokube.ai",
        }
    )

    assert result == {
        "messages": [
            AIMessage(
                content=(
                    "prokube helps teams run AI infrastructure.\n\n"
                    "Source: https://prokube.ai"
                )
            )
        ]
    }
