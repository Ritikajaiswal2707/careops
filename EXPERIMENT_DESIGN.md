# Experiment design: does model-prioritized outreach reduce disruptions?

**Status: proposed; not run.** All volumes and baseline rates below come from the synthetic dataset. No real patients were contacted and no causal intervention effect has been measured.

## Hypothesis

Proactive outreach (for example, a confirmation request or reschedule offer) to eligible appointments in the model's top-20% risk band reduces disruption (No-Show or Cancelled) relative to the existing workflow.

## Proposed design

- **Eligible population:** appointments falling in the top 20% of predicted disruption risk, computed using the leakage-fixed `model/disruption_model.py` model.
- **Control:** existing coordinator workflow; no model-triggered intervention.
- **Treatment:** a coordinator-reviewed CareOps-supported intervention, recorded as delivered only when it actually is.
- **Primary outcome:** appointment-level disruption rate (No-Show or Cancelled) by the originally scheduled visit date.
- **Guardrails:** coordinator minutes per eligible appointment; patient complaint/opt-out rate; completion rate in the non-flagged 80%; safety incidents; and unavailable/missed outcomes.
- **Randomization:** do not finalize the unit until repeat-visit contamination is addressed. In the August synthetic test set, the flagged band contains 631 appointments from 453 patients; 122 patients have more than one flagged appointment. Patient-level assignment is safer if an intervention may affect later appointments. If randomizing appointments, prespecify cluster-robust inference and prevent coordinators from switching arms. A statistician should finalize the protocol.

## Baseline and eligible volume

The August test period has 3,155 appointments, 811 disruptions overall (25.7%). The top-20% flagged group contains 631 appointments and 212 disruptions, giving a **33.6% flagged-group disruption rate**. Since the experiment randomizes within the flagged group, 33.6%—not the overall 25.7%—is the planning baseline for the simple appointment-level calculation below.

The synthetic dataset implies approximately 3,333 total appointments per month (10,000 synthetic appointments across 90 days, scaled to a 30-day month); applying a 20% flagged share gives about **667 eligible appointments per month**. This is a synthetic-volume planning assumption, not a real operating-volume claim.

## Sample-size sensitivity (unadjusted planning estimates)

`python model/experiment_power.py` reproduces the table. The calculation uses a two-sided two-proportion normal approximation, alpha = 0.05 and power = 0.80. Relative reductions are hypothetical treatment effects, **not estimates from the model**.

| Assumed relative reduction in flagged-group disruption | Control rate | Treatment rate | Approx. per arm | Total | Months at ~667 eligible/month |
|---:|---:|---:|---:|---:|---:|
| 10% | 33.6% | 30.2% | 3,021 | 6,042 | 9.1 |
| 15% | 33.6% | 28.6% | 1,323 | 2,646 | 4.0 |
| 20% | 33.6% | 26.9% | 733 | 1,466 | 2.2 |
| 25% | 33.6% | 25.2% | 461 | 922 | 1.4 |

The 14.9% value in `model/economics_summary.json` is a **top-down economic break-even intervention-success assumption**. It is not a predicted relative reduction in disruption and should not be inserted into this table as though the two quantities were interchangeable.

These counts assume independent appointment outcomes, complete observation, stable volume, and no attrition. They do **not** account for within-patient correlation or patient-level randomization. A rough overall August intraclass correlation estimate is about 0.05, while the flagged-only estimate is unstable/negative; neither is reliable enough to apply as a definite design effect. Recalculate after choosing the randomization unit and collecting appropriate variance estimates. The estimated months are optimistic if some visits are excluded, outcomes are missing, or eligible volume fluctuates.

## Analysis plan

1. Freeze model version, risk cutoff, eligibility rules, and intervention definitions before assignment.
2. Prespecify the primary analysis as intention-to-treat by assigned arm.
3. Report absolute risk difference and relative risk reduction with confidence intervals, alongside denominators and missing outcomes.
4. If patients contribute multiple appointments, use patient-level randomization or a prespecified method accounting for within-patient clustering.
5. Track guardrails regardless of whether the primary outcome improves. Do not promote automation solely because the primary metric improves.
6. Define positive, null, and harmful outcomes before launch. A null result is evidence that the intervention has not demonstrated impact under this design—not proof that the model or intervention can never work.

## Economic interpretation

`model/economics_simulation.py` assumes a 35% intervention success rate and placeholder revenue/cost inputs. Its top-down calculation estimates 74 recovered visits and +₹33,970 modelled net value. The capacity-constrained case-by-case simulation estimates 16 recovered visits and −₹12,850 because 164 of 212 flagged true disruptions have no eligible backup candidate. Both are simulations, not measured business outcomes. The 14.9% break-even success rate belongs to the top-down calculation and is not a validated business threshold when recovery capacity is constrained.

## Separate validation needed for LLM behaviour

The 103-message held-out intent scores are offline results using saved blind predictions; they are not a live Gemini/Anthropic API benchmark. A separate metered evaluation is needed for deployed extraction quality, schema-validity, latency, cost, failure rate, model-version stability, and privacy handling before using actual patient messages. Do not send real patient data to this portfolio demo.
