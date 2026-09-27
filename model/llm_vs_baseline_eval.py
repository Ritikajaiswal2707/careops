"""
Module 2b: rule-based extractor vs. LLM, on a held-out set.

The 100% agreement number reported by communication_intelligence.py is
measured against the rules' *own* training labels -- the source CSV has
only 10 unique messages, and extracted_intent was already in the dataset
the rules were written to match. That number shows the rules reproduce
their own targets, not that they generalize to phrasing they haven't seen.

This module is the actual test: a held-out set of 103 messages, hand-labeled
(full gold structure -- intent, temporal signal, and reason, not just
intent), written independently of communications.csv's 10 templates --
deliberately including English, Hindi, Hinglish, typos, indirect/no-keyword
phrasing, sarcasm, compound requests, and a spread of temporal expressions
(explicit weekday, "next week", "next <weekday>", "kal"/tomorrow, weekend,
"after N days", and vague/no signal at all) -- the rule set was never tuned
against most of this. It scores, on the same set:
  1. The existing rule-based extractor (runs unconditionally -- no dependency)
  2. An LLM call via the Anthropic API, prompted to return the full
     structured extraction as JSON (runs only if ANTHROPIC_API_KEY is set --
     this sandbox has no key wired in, same limitation the README already
     discloses for communication_intelligence.py)

Metrics computed for whichever side(s) actually ran:
  - Intent accuracy + macro/per-class F1 (not just overall accuracy, which
    hides class imbalance -- Confirm is common and easy; Cancel/Reschedule
    without keywords are rare and hard, and a macro F1 doesn't let a strong
    Confirm score hide weak Cancel/Reschedule performance)
  - Temporal extraction accuracy (exact match on preferred_day, next_week,
    relative_day, offset_days as a tuple -- partial credit isn't given,
    because a wrong date is operationally a wrong date)
  - Reason extraction accuracy (exact match against the 3-category gold set)
  - JSON validity rate (trivially 100% for the rule-based side, since it's
    native Python; the real question is whether the LLM's output parses
    cleanly every time when asked to emit JSON)
  - Abstention rate (share of predictions the extractor itself flags as
    Unclear -- a system that abstains honestly is different from one that
    guesses wrong confidently, and this number distinguishes them)
  - Cost/message and latency/message (rule-based is $0 and sub-millisecond
    by construction; LLM numbers are only reported when a live run happened
    -- never estimated)

This is the experiment the case study argues for: does an LLM improve
intent + temporal + reason extraction enough to justify its added
cost/latency/complexity over a free, instant, fully-offline rule-based
baseline? Answering that requires actually running both sides -- this
script is set up to do that the moment an API key is available; it does
not simulate or assume an LLM result.
"""
import json
import os
import time
from collections import defaultdict
from communication_intelligence import extract_intent

# ---- Held-out set --------------------------------------------------------
# Hand-labeled, written independently of communications.csv's 10 message
# templates. Every item carries the FULL gold structure the product needs
# (intent, preferred_day, next_week, relative_day, offset_days, reason) --
# not just intent -- because intent-only was the gap the P0 review flagged:
# a coordinator seeing "Reschedule" still needs to know to when and why.
#
# Categories, roughly balanced against real-world class imbalance (Confirm
# is the most common real message; Cancel and no-keyword Reschedule are
# rarer but higher-stakes to get right):
#   - Confirm: explicit, minimal ("ok", "yep"), Hinglish, typo'd
#   - Reschedule: explicit weekday, "next week", "next <weekday>", weekend,
#     "kal"/tomorrow, "after N days", vague/no day named, no reschedule
#     keyword at all, each with a mix of doctor/work/late/no reason
#   - Cancel: explicit keyword, and indirect phrasing with no cancel keyword
#   - Unclear: genuinely ambiguous, non-committal, or off-topic
#   - No Response: empty / whitespace-only
HELD_OUT_SET = [
    # -- Confirm --------------------------------------------------------
    {"message": "Confirmed, thank you!", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "haan bilkul, wahi time pe aa jaana", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "yes see u then", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "ok", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "sab thik hai, appointment as is", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "great, see you then!", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "yep all good", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "theek h chalega", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "haanji sab sahi hai", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "running 10 min behind, still coming though", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "haan aaj hi aa jaana, sab plan same hai", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "confrm h, no changes", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "sounds good, thanks!", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "we'll be home, come as planned", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "haa theek hai aaj wala time hi rakho", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "cool, works for us", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "yeah that's fine, no need to change anything", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "ji haan, wahi time theek hai", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "k", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "sahi hai bhai, aa jao", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},

    # -- Reschedule: explicit weekday named -----------------------------
    {"message": "Kal thoda late ho jayega, Saturday kar sakte ho?", "intent": "Reschedule", "preferred_day": "Saturday", "next_week": False, "relative_day": "tomorrow", "offset_days": None, "reason": "Provider/patient running late"},
    {"message": "any chance of moving to next monday", "intent": "Reschedule", "preferred_day": "Monday", "next_week": True, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "can we push it out a bit? maybe next tuesday", "intent": "Reschedule", "preferred_day": "Tuesday", "next_week": True, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "doctor visit hai usi din, reschedule possible? Friday theek rahega", "intent": "Reschedule", "preferred_day": "Friday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},
    {"message": "office ka kaam aa gaya, can we shift to wednesday", "intent": "Reschedule", "preferred_day": "Wednesday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},
    {"message": "sorry cant do thursday, kar sakte ho on sunday instead?", "intent": "Reschedule", "preferred_day": "Sunday", "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "kl subah nahi ho payega, weekend pe kar sakte?", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": "weekend", "offset_days": None, "reason": None},
    {"message": "work call chal raha hoga us time, shift to thursday please", "intent": "Reschedule", "preferred_day": "Thursday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},
    {"message": "doctor ke pass jaana hai wahi din, postpone to next friday please", "intent": "Reschedule", "preferred_day": "Friday", "next_week": True, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},
    {"message": "running late from office, possible on saturday?", "intent": "Reschedule", "preferred_day": "Saturday", "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},

    # -- Reschedule: "next week" / no day named -------------------------
    {"message": "Hey, can we push this to sometime next week?", "intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "postponing to next week please", "intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "not today, some other day", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "she's not well, we'll call to rebook", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "Sorry yaar, kal nahi ho payega, agle hafte try karte hain", "intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": "tomorrow", "offset_days": None, "reason": None},
    {"message": "doctor appointment aa gaya isi hafte, agle hafte dekh lete hain", "intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},
    {"message": "kuch kaam aa gaya office se, thoda aage badha do please", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},
    {"message": "can we look at another day this week, doctor ka appointment clash ho raha hai", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},

    # -- Reschedule: offset days / time-of-day shift --------------------
    {"message": "is it possible after 5 days?", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 5, "reason": None},
    {"message": "can we do it after 3 days instead, works better for us", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 3, "reason": None},
    {"message": "can u come a bit later in the day instead? like evening?", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "possible after 7 days? going out of town till then", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 7, "reason": None},
    {"message": "after 2 din possible hai kya, kal doctor ke paas jaana hai", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 2, "reason": "Conflicting doctor visit"},

    # -- Reschedule: no keyword at all / typos ---------------------------
    {"message": "we're not free tomorrow anymore, works some other time?", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": "tomorrow", "offset_days": None, "reason": None},
    {"message": "cant make it kal, kabhi aur din try karein?", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": "tomorrow", "offset_days": None, "reason": None},
    {"message": "somthing came up, cant do satuday, wat about sundy", "intent": "Reschedule", "preferred_day": "Sunday", "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "we're out for a family fn that day, dusre din dekh lo koi", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "resched krna h yr, mon nahi ho payega ab", "intent": "Reschedule", "preferred_day": "Monday", "next_week": False, "relative_day": None, "offset_days": None, "reason": None},

    # -- Cancel: explicit keyword -----------------------------------------
    {"message": "I don't think I can make it anymore, please cancel", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "mujhe nahi karna ab, cancel kar do please", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "aaj cancel, kal aa jaunga", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": "tomorrow", "offset_days": None, "reason": None},
    {"message": "Is week cancel karna padega", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "plz cancle, cant come today", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "cant do it, sorry, please cancel this one", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "nahi aa payenge is baar, cancel kar dena", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},

    # -- Cancel: indirect, no keyword --------------------------------------
    {"message": "we're not going to need this appointment", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "please don't come, we're out of town", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "no thanks, we'll skip this one", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "we need to stop this service", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "cant do it, sorry", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "patient ko hospital admit karwa diya hai, ab ye visit nahi chahiye", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "we've decided to go with a different arrangement, don't send anyone", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "not needed anymore, sorry for the trouble", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "papa ab theek hain, ab is care ki zaroorat nahi", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "we moved to another city, please close this out", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},

    # -- Unclear / ambiguous / off-topic ------------------------------------
    {"message": "not sure, will confirm later", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "let me check with my husband and get back to you", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "kaun bol raha hai ye?", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "abhi decide nahi kiya, batayenge", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "why did the last person come so late last time", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "kitna charge hoga is visit ka", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "hmm", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "acha dekhte hain", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "which provider is coming this time", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "call me when you're close", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "???", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "we'll see how mummy is feeling that day", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},

    # -- No Response ---------------------------------------------------------
    {"message": "", "intent": "No Response", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "   ", "intent": "No Response", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},

    # -- Extra spread: sarcasm, compound requests, Hindi-script-only,
    #    and more temporal variety, added to push held-out coverage closer
    #    to the 100-200 message range recommended for this benchmark -----
    {"message": "oh sure, because today was SO convenient. can we do next week instead", "intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # sarcasm wrapped around a real ask
    {"message": "cancel kar do na, itni baar mat pucho", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # irritated tone, still a clear cancel
    {"message": "aaj cancel karo aur agle hafte Wednesday ko fix kar do", "intent": "Cancel", "preferred_day": "Wednesday", "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # compound: cancel today AND reschedule detail in one message -- intent should read as the dominant action (Cancel of today's visit)
    {"message": "मुझे कल नहीं होगा, अगले हफ्ते कर लेंगे", "intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": "tomorrow", "offset_days": None, "reason": None},  # Devanagari script, no Latin transliteration at all
    {"message": "ठीक है, वही समय पर आ जाना", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # Devanagari confirm
    {"message": "अभी कैंसिल कर दो प्लीज़", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # Devanagari cancel
    {"message": "can we do next next week, this week is packed", "intent": "Reschedule", "preferred_day": None, "next_week": True, "relative_day": None, "offset_days": None, "reason": None},  # "next next week" -- deliberately unusual phrasing
    {"message": "possible thursday ya friday, jo bhi mile", "intent": "Reschedule", "preferred_day": "Thursday", "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # two days offered -- gold takes the first named, since parse_temporal only extracts one
    {"message": "not this week, maybe start of next month", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},  # vague far-future ask, no usable structured signal at all
    {"message": "provider hamesha late aata hai, isliye hum bhi late honge, evening slot possible?", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Provider/patient running late"},
    {"message": "beta ka school event hai us din, kisi aur din try karo please", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "we'll be traveling, can you push it after 10 days", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 10, "reason": None},
    {"message": "aftr 4 dayss possible? thanks", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": 4, "reason": None},  # typo'd offset phrasing
    {"message": "we don't want this service anymore, please discontinue", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "ab zaroorat nahi hai iski, dhanyawad", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "sorry to say but cancel this permanently", "intent": "Cancel", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "haa sab plan wahi hai, koi change nahi", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "confirm, bas thoda pehle aa jaana agar ho sake", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "yup, all set on our end", "intent": "Confirm", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "does the provider carry their own equipment or should we arrange something", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "aap kaun bol rahe ho, ye number kisne diya", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "matlab kya hua, samajh nahi aaya", "intent": "Unclear", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": None},
    {"message": "next tuesday ko doctor ka appointment hai, uske baad kisi din kar lo", "intent": "Reschedule", "preferred_day": "Tuesday", "next_week": True, "relative_day": None, "offset_days": None, "reason": "Conflicting doctor visit"},
    {"message": "office se abhi nikal nahi paunga time pe, thoda evening mein shift karo", "intent": "Reschedule", "preferred_day": None, "next_week": False, "relative_day": None, "offset_days": None, "reason": "Work conflict"},
]


def _per_class_f1(pairs, labels):
    """pairs: list of (true, pred). Returns {label: f1} and macro F1."""
    f1s = {}
    for label in labels:
        tp = sum(1 for t, p in pairs if t == label and p == label)
        fp = sum(1 for t, p in pairs if t != label and p == label)
        fn = sum(1 for t, p in pairs if t == label and p != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1s[label] = round(f1, 3)
    macro = round(sum(f1s.values()) / len(f1s), 3) if f1s else 0.0
    return f1s, macro


def _score(predictions):
    """predictions: list of dicts with true_* and pred_* keys per case, plus
    optional 'json_valid' and 'latency_s'. Returns the full metric bundle."""
    n = len(predictions)
    intent_labels = sorted({p["true_intent"] for p in predictions} | {p["pred_intent"] for p in predictions})
    intent_pairs = [(p["true_intent"], p["pred_intent"]) for p in predictions]
    intent_f1_by_class, intent_macro_f1 = _per_class_f1(intent_pairs, intent_labels)
    intent_accuracy = sum(t == pr for t, pr in intent_pairs) / n

    temporal_correct = sum(
        (p["true_temporal"] == p["pred_temporal"]) for p in predictions
    )
    reason_correct = sum(p["true_reason"] == p["pred_reason"] for p in predictions)
    abstentions = sum(1 for p in predictions if p["pred_intent"] == "Unclear")
    json_valid = [p.get("json_valid") for p in predictions if p.get("json_valid") is not None]

    return {
        "n": n,
        "intent_accuracy": round(intent_accuracy, 3),
        "intent_macro_f1": intent_macro_f1,
        "intent_f1_by_class": intent_f1_by_class,
        "temporal_extraction_accuracy": round(temporal_correct / n, 3),
        "reason_extraction_accuracy": round(reason_correct / n, 3),
        "abstention_rate": round(abstentions / n, 3),
        "json_validity_rate": round(sum(json_valid) / len(json_valid), 3) if json_valid else None,
    }


def run_rule_based_eval():
    predictions = []
    total_latency = 0.0
    for case in HELD_OUT_SET:
        t0 = time.perf_counter()
        pred = extract_intent(case["message"])
        total_latency += time.perf_counter() - t0
        predictions.append({
            "message": case["message"],
            "true_intent": case["intent"],
            "pred_intent": pred["intent"],
            "true_temporal": (case["preferred_day"], case["next_week"], case["relative_day"], case["offset_days"]),
            "pred_temporal": (pred["preferred_day"], pred["next_week"], pred["relative_day"], pred["offset_days"]),
            "true_reason": case["reason"],
            "pred_reason": pred["reason"],
            "json_valid": True,  # native Python dict -- always structurally valid
        })
    metrics = _score(predictions)
    metrics["cost_per_message_inr"] = 0.0
    metrics["avg_latency_ms"] = round((total_latency / len(predictions)) * 1000, 4)
    misclassified = [p for p in predictions if p["true_intent"] != p["pred_intent"]]
    return predictions, metrics, misclassified


def run_llm_eval():
    """
    Calls the Anthropic API to extract the FULL structure (intent,
    preferred_day, next_week, relative_day, offset_days, reason) for the
    same held-out set, as JSON. Only runs if ANTHROPIC_API_KEY is set --
    this sandbox does not have one wired in (same disclosed limitation as
    communication_intelligence.py's docstring). Returns None if unavailable,
    rather than fabricating or estimating a result. This is deliberately the
    same architecture P0-6 argues for: the LLM only does "understand ->
    structured JSON", never scheduling logic.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    import anthropic  # local import: only needed on this path
    client = anthropic.Anthropic(api_key=api_key)

    system = (
        "Extract structured information from a home-healthcare patient "
        "message (English, Hindi, Hinglish, or a mix, possibly with typos). "
        "Respond with ONLY a JSON object, no other text, matching exactly:\n"
        '{"intent": "Confirm"|"Reschedule"|"Cancel"|"Unclear"|"No Response", '
        '"preferred_day": "Monday".."Sunday" or null, '
        '"next_week": true|false, '
        '"relative_day": "tomorrow"|"weekend"|null, '
        '"offset_days": integer or null, '
        '"reason": "Conflicting doctor visit"|"Work conflict"|'
        '"Provider/patient running late"|null}'
    )

    # Illustrative INR pricing for the model used here, at the time of
    # writing -- not fetched live, so treat this as a placeholder to
    # recompute against current published rates before quoting it externally.
    INPUT_PER_TOKEN_INR = 0.00025
    OUTPUT_PER_TOKEN_INR = 0.00125

    predictions = []
    total_latency = 0.0
    total_cost = 0.0
    for case in HELD_OUT_SET:
        t0 = time.perf_counter()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": case["message"] or "(empty message)"}],
        )
        total_latency += time.perf_counter() - t0
        total_cost += (resp.usage.input_tokens * INPUT_PER_TOKEN_INR
                       + resp.usage.output_tokens * OUTPUT_PER_TOKEN_INR)

        raw = resp.content[0].text.strip()
        try:
            parsed = json.loads(raw)
            json_valid = True
        except json.JSONDecodeError:
            parsed = {}
            json_valid = False

        predictions.append({
            "message": case["message"],
            "true_intent": case["intent"],
            "pred_intent": parsed.get("intent", "PARSE_ERROR"),
            "true_temporal": (case["preferred_day"], case["next_week"], case["relative_day"], case["offset_days"]),
            "pred_temporal": (parsed.get("preferred_day"), parsed.get("next_week", False),
                               parsed.get("relative_day"), parsed.get("offset_days")),
            "true_reason": case["reason"],
            "pred_reason": parsed.get("reason"),
            "json_valid": json_valid,
        })

    metrics = _score(predictions)
    metrics["cost_per_message_inr"] = round(total_cost / len(predictions), 4)
    metrics["avg_latency_ms"] = round((total_latency / len(predictions)) * 1000, 1)
    misclassified = [p for p in predictions if p["true_intent"] != p["pred_intent"]]
    return predictions, metrics, misclassified


if __name__ == "__main__":
    rule_predictions, rule_metrics, rule_misclassified = run_rule_based_eval()
    print(f"Rule-based extractor on {rule_metrics['n']} held-out messages:")
    print(f"  intent accuracy      {rule_metrics['intent_accuracy']:.1%}  (macro F1 {rule_metrics['intent_macro_f1']})")
    print(f"  per-class F1         {rule_metrics['intent_f1_by_class']}")
    print(f"  temporal accuracy    {rule_metrics['temporal_extraction_accuracy']:.1%}")
    print(f"  reason accuracy      {rule_metrics['reason_extraction_accuracy']:.1%}")
    print(f"  abstention rate      {rule_metrics['abstention_rate']:.1%}")
    print(f"  cost / latency       Rs.{rule_metrics['cost_per_message_inr']} / {rule_metrics['avg_latency_ms']} ms per message")

    output = {
        "held_out_set_size": len(HELD_OUT_SET),
        "rule_based": {"metrics": rule_metrics, "misclassified": rule_misclassified},
        "llm": None,
    }

    llm_out = run_llm_eval()
    if llm_out:
        llm_predictions, llm_metrics, llm_misclassified = llm_out
        print(f"\nLLM (claude-sonnet-4-6), structured JSON extraction, same {llm_metrics['n']} messages:")
        print(f"  intent accuracy      {llm_metrics['intent_accuracy']:.1%}  (macro F1 {llm_metrics['intent_macro_f1']})")
        print(f"  temporal accuracy    {llm_metrics['temporal_extraction_accuracy']:.1%}")
        print(f"  reason accuracy      {llm_metrics['reason_extraction_accuracy']:.1%}")
        print(f"  JSON validity        {llm_metrics['json_validity_rate']:.1%}")
        print(f"  cost / latency       Rs.{llm_metrics['cost_per_message_inr']} / {llm_metrics['avg_latency_ms']} ms per message")
        output["llm"] = {"metrics": llm_metrics, "misclassified": llm_misclassified}
    else:
        print("\nLLM comparison skipped: no ANTHROPIC_API_KEY in this environment. "
              "Set the key and re-run to get the actual head-to-head result across "
              "all five metrics -- this script does not simulate or assume one.")

    with open("llm_vs_baseline_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print("\nwrote model/llm_vs_baseline_results.json")
