#!/usr/bin/env python3
"""
parliament/test_channel_taint.py
=================================

Pure unit tests for is_source_tool()'s naming-convention-agnostic matching
in channel_taint.py. No server, no ChromaDB, no embedding model.

Background: CHANNEL's source-tool recognition was originally scoped
entirely to InjecAgent's PascalCase vendor-prefixed naming convention
(SOURCE_TOOLS_EXACT + a PascalCase-only regex). A ground-truth replay
against real AgentDojo trajectories found this meant CHANNEL had ZERO
effective coverage on AgentDojo's snake_case tool surface, regardless of
what a tool actually did -- confirmed by testing 5 real source tools
(e.g. AmazonViewSavedAddresses) against structurally-identical snake_case
names, all of which failed to match.

The fix (is_source_tool()'s third tier) tokenizes any naming convention
into a common lowercase form and checks the SAME existing vocabulary via
token/bigram matching -- no new nouns or verbs, only convention-agnostic
matching of what was already there.

These two tests pin the exact regression found and fixed during that work,
so they cannot silently reappear:

1. test_source_tool_recognizes_snake_case_compound_noun -- the fix's
   positive case: TwilioGetPhoneNumberInfo's snake_case equivalent
   (twilio_get_phone_number_info) was NOT recognized by an earlier draft
   of the token-matching logic, because "PhoneNumber" tokenizes to two
   separate tokens (['phone','number']) and an exact-single-token-
   membership check missed the compound. Fixed via a bounded adjacent-
   token-pair check.

2. test_source_tool_does_not_match_get_user_information -- the fix's
   negative case: a DIFFERENT earlier draft (joining all tokens into one
   unbounded string and substring-matching) caused a real false positive
   on get_user_information, because 'get'+'user'+'information' joins to
   'getuserinformation', which contains 'userinfo' as an accidental
   cross-token-boundary substring -- even though get_user_information is
   a confirmed-benign AgentDojo read (travel/banking suites) that must
   NEVER taint a session.

Run before merging any changes to channel_taint.py's is_source_tool().

Usage:
    pytest parliament/test_channel_taint.py -v
or:
    python parliament/test_channel_taint.py
"""

from __future__ import annotations

from .channel_taint import is_source_tool, SOURCE_TOOLS_EXACT


# ──────────────────────────────────────────────────────────────────────────────
# The two permanent regression tests
# ──────────────────────────────────────────────────────────────────────────────

def test_source_tool_recognizes_snake_case_compound_noun():
    """twilio_get_phone_number_info -- snake_case equivalent of the real
    InjecAgent source tool TwilioGetPhoneNumberInfo -- must be recognized
    as a source tool. Regression test for a real bug found during the
    naming-convention fix: an exact-single-token-membership check missed
    this because 'PhoneNumber' tokenizes to two tokens, neither of which
    alone is the sensitive noun."""
    assert is_source_tool("twilio_get_phone_number_info") is True
    # The PascalCase original must still match too (unchanged behavior).
    assert is_source_tool("TwilioGetPhoneNumberInfo") is True


def test_source_tool_does_not_match_get_user_information():
    """get_user_information is a confirmed-benign AgentDojo read (appears
    in real travel/banking user_task ground truths with no attack
    association) and must NEVER be classified as a source tool. Regression
    test for a real false positive found during the naming-convention fix:
    an earlier draft joined all tokens into one unbounded string
    ('getuserinformation') and substring-matched against it, which
    accidentally matched 'userinfo' across a token boundary that was never
    intended to align that way."""
    assert is_source_tool("get_user_information") is False
    assert is_source_tool("get_user_info") is False


# ──────────────────────────────────────────────────────────────────────────────
# Broader coverage: convention-agnostic matching, AgentDojo exclusions,
# and the original InjecAgent vocabulary staying intact.
# ──────────────────────────────────────────────────────────────────────────────

def test_snake_case_equivalents_of_real_source_tools_now_recognized():
    """Confirms the naming-convention fix actually closes the gap it was
    built for: snake_case equivalents of real SOURCE_TOOLS_EXACT entries
    must now match, even though the exact-match list and the PascalCase-
    only regex both structurally cannot match them."""
    cases = [
        "amazon_view_saved_addresses",
        "the23andme_get_genetic_data",
        "get_saved_password",
        "view_health_records",
    ]
    for tool in cases:
        assert is_source_tool(tool) is True, f"{tool} should be recognized as a source tool"


def test_agentdojo_tool_names_deliberately_not_recognized():
    """AgentDojo's own tool names must stay unrecognized as sources --
    deliberate, not an oversight. Confirmed via direct testing against
    real AgentDojo ground_truth() data that adding these as source
    triggers would false-positive on 2 real workspace user_tasks and
    9/21 (43%) of slack user_tasks, where the same read-then-send shape
    is the correct, user-requested action, not an attack. Same
    conflict already documented for banking's
    get_most_recent_transactions/get_scheduled_transactions."""
    must_stay_false = [
        "search_emails", "read_channel_messages", "get_channels",
        "get_all_hotels_in_city", "get_hotels_prices",
        "read_file", "get_balance", "get_most_recent_transactions",
        "get_scheduled_transactions", "get_day_calendar_events",
        "get_rating_reviews_for_hotels", "get_webpage", "get_current_day",
        "get_unread_emails", "search_calendar_events",
    ]
    for tool in must_stay_false:
        assert is_source_tool(tool) is False, f"{tool} should NOT be recognized as a source tool"


def test_all_32_injecagent_source_tools_still_match():
    """The original 32-entry InjecAgent exact-match vocabulary must be
    completely unaffected by the naming-convention fix."""
    for tool in SOURCE_TOOLS_EXACT:
        assert is_source_tool(tool) is True, f"{tool} regressed"


if __name__ == "__main__":
    test_source_tool_recognizes_snake_case_compound_noun()
    test_source_tool_does_not_match_get_user_information()
    test_snake_case_equivalents_of_real_source_tools_now_recognized()
    test_agentdojo_tool_names_deliberately_not_recognized()
    test_all_32_injecagent_source_tools_still_match()
    print("All channel_taint tests passed.")
