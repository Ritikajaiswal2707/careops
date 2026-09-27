my_predictions = [
    # ---------------------------------------------------------------------
    # These 103 predictions were produced BLIND: read from a plain numbered
    # list of messages only (see the "blind classification" step in the
    # case-study notes), with no access to communication_eval.json's gold
    # labels at the time each line below was written. They were then, and
    # only then, scored against the gold set in llm_direct_eval.py.
    #
    # Why this file exists instead of a real API call: this environment has
    # no ANTHROPIC_API_KEY configured, and provisioning one specifically for
    # this benchmark was declined (no willingness to pay for the ~103 calls
    # this would cost). Claude -- the same model family
    # llm_vs_baseline_eval.py's run_llm_eval() would call via the API --
    # performed the extraction directly instead, using the identical schema
    # from that function's system prompt. This is a genuine test of LLM
    # extraction quality (intent/temporal/reason accuracy); it does NOT
    # produce a real cost-per-message or latency number, because no metered
    # API round-trip happened. Those two fields are reported as null, not
    # estimated, in llm_vs_baseline_results.json -- see llm_direct_eval.py.
    #
    # Schema note: this list was frozen under the ORIGINAL 5-field schema
    # (intent, preferred_day, next_week, relative_day, offset_days, reason).
    # A later taxonomy fix added a 6th field, cancel_current, to represent
    # compound "cancel today's + book a new one" requests (cases 50 and 81
    # below) without forcing them into a single Cancel-or-Reschedule label --
    # see communication_intelligence.py and README. These predictions are
    # NOT retroactively scored on cancel_current (llm_direct_eval.py reports
    # that metric as null for this path) because backfilling a value now
    # would mean grading hindsight, not a blind answer. What DOES carry over
    # honestly: the gold intent label for 50/81 changed from Cancel to
    # Reschedule as part of that same fix, and Claude's blind intent
    # prediction for both was already "Reschedule" (see below) -- so
    # rescoring against the corrected gold is fair (it's a label fix, not
    # new information handed to the predictor) and these two flip from
    # errors to correct.
    # ---------------------------------------------------------------------
    # 0-19: Confirm cluster
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 0
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 1
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 2
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 3 "ok"
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 4
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 5
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 6
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 7
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 8
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Provider/patient running late"},  # 9 "running 10 min behind, still coming"
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 10
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 11 "confrm h"
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 12
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 13
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 14
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 15
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 16
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 17
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 18 "k"
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 19

    # 20-47: Reschedule cluster
    {"intent": "Reschedule", "preferred_day": "Saturday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Provider/patient running late"},  # 20
    {"intent": "Reschedule", "preferred_day": "Monday", "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 21
    {"intent": "Reschedule", "preferred_day": "Tuesday", "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 22
    {"intent": "Reschedule", "preferred_day": "Friday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},  # 23
    {"intent": "Reschedule", "preferred_day": "Wednesday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},  # 24
    {"intent": "Reschedule", "preferred_day": "Sunday", "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 25
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": "weekend", "offset_days": None, "reason": None},  # 26
    {"intent": "Reschedule", "preferred_day": "Thursday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},  # 27
    {"intent": "Reschedule", "preferred_day": "Friday", "next_week": True, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},  # 28
    {"intent": "Reschedule", "preferred_day": "Saturday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Provider/patient running late"},  # 29
    {"intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 30
    {"intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 31
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 32
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 33
    {"intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 34
    {"intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},  # 35
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},  # 36
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},  # 37
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 5, "reason": None},  # 38
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 3, "reason": None},  # 39
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 40 (time-of-day, no day change)
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 7, "reason": None},  # 41
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 2, "reason": "Conflicting doctor visit"},  # 42
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 43
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 44
    {"intent": "Reschedule", "preferred_day": "Sunday", "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 45
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 46
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 47

    # 48-64: Cancel cluster
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 48
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 49
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": "tomorrow", "offset_days": None, "reason": None},  # 50 "aaj cancel, kal aa jaunga"
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 51
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 52
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 53
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 54
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 55
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 56
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 57
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 58
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 59
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 60
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 61
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 62
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 63
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 64

    # 65-76: Unclear cluster
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 65
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 66
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 67
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 68
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 69
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 70
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 71
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 72
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 73
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 74 "call me when you're close"
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 75 "???"
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 76

    # 77-78: No Response
    {"intent": "No Response", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 77 empty
    {"intent": "No Response", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 78 whitespace

    # 79-102: mixed / sarcasm / compound / Devanagari / vague
    {"intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 79 sarcastic, wants next week
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 80
    {"intent": "Reschedule", "preferred_day": "Wednesday", "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 81 compound cancel+rebook
    {"intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 82 Devanagari
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 83 Devanagari
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 84 Devanagari
    {"intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # 85 "next next week" (approximated)
    {"intent": "Reschedule", "preferred_day": "Thursday", "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 86 Thu-or-Fri, picked first
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 87 "start of next month" -- deliberately not next_week
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Provider/patient running late"},  # 88 evening slot, same day
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 89 school event
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 10, "reason": None},  # 90
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 4, "reason": None},  # 91
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 92
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 93
    {"intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 94
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 95
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 96
    {"intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 97
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 98
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 99
    {"intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # 100
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},  # 101
    {"intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},  # 102
]
