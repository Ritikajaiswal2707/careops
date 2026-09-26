# AI Care Operations Copilot

A portfolio project exploring how AI can predict, explain, and help recover from disruptions in home healthcare delivery — with a specific focus on the operational realities of India's home-care market: contractual/gig service providers with variable day-to-day availability, elderly patients who often can't self-report precise location, and delay cascades caused by traffic, weather, or overruns.

**This is a PM portfolio project.** All data is synthetic/simulated. It exists to demonstrate product thinking — problem framing, prioritization, tradeoff decisions, and AI-product judgment — not to claim production-grade engineering or real-world validated outcomes.

## Structure

- `data/` — synthetic 6-table dataset (providers, patients, appointments, operational, communications, availability) modeling a home-care operation across 5 Indian cities, 20 clinicians, 2,000 patients, 10,000 appointments
- `model/disruption_model.py` — a deliberately simple, explainable logistic regression predicting visit disruption risk, plus a rule-based plain-language explanation layer and threshold/precision-recall tradeoff analysis
- `dashboard/index.html` — an interactive "Today's Care Operations" prototype: a capacity-aware risk triage view, and a delay/cascade-notification view

## Known limitations (intentional, and part of the case study)

- The model over-indexes on first-time-patient status as a risk signal — flagged here as a fairness/design concern requiring mitigation before any real use, not something smoothed over
- Risk tiering is directionally reliable in aggregate but noisy on any single simulated day, given the model's modest predictive strength (this is honestly reported, not inflated)
- No live integrations (WhatsApp, real scheduling/optimization engine) — those are described as proposed architecture in the accompanying case study, not built here

## Full case study

The complete product narrative — problem framing, autonomy-level framework, prioritization decisions, and simulated impact — lives in the accompanying case study deck (linked from the portfolio).
