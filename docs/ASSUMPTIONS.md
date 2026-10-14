# CareOps — Assumptions

## Known assumptions

- Coordinator capacity is modeled as a fixed top-20% intervention band.
- The risk model uses synthetic data.
- Provider availability is partially simulated (future availability is generated from each provider's historical rate).
- Provider proximity is inferred because provider GPS is unavailable.
- Provider service capability is represented using a business-rule mapping, not learned from data.
- Economics contain placeholder assumptions (intervention success rate, revenue per visit, coordinator hourly cost).
- Patient accept/decline in the outcome simulation is a coin flip at a placeholder rate, not a real response.
- LLM cost and latency are not measured. The 103-message LLM/hybrid evaluation reuses saved blind offline predictions; it is not a live Gemini/Anthropic API benchmark.
- Live API calls can invoke an external model only when configured, but the dashboard snapshot pipeline never calls an LLM. The demo does not execute real patient or scheduling actions.

## Validation required before production

- Validate coordinator capacity assumptions
- Validate provider availability
- Measure intervention success rate
- Measure recovery feasibility
- Validate AI quality on a larger real labeled set
- Measure cost and latency
- Establish privacy controls
- Establish escalation SLAs
