# Visit-report thresholds

> **Not validated for clinical use.** These lines only decide whether a coordinator looks at a visit report before the family update goes out. They are not diagnoses, alerts to clinicians, or treatment guidance. A real deployment would have them set and signed off by the agency's clinical lead.

Two kinds of line are used (see `model/visit_report.py`):

- **Red flag:** the report is held for the coordinator, and the family update waits.
- **Outside the usual range:** shown to the coordinator in amber. It does not hold the report on its own.

| Reading | Red flag (held for review) | Outside usual range (shown only) | Where the line comes from |
|---|---|---|---|
| Blood pressure, systolic | below 90 or 180 and above | below 100 or 140 and above | 180 matches the ACC/AHA 2017 "hypertensive crisis" line; 140 is the start of stage 2 hypertension ([ACC](https://acc.org/Latest-in-Cardiology/Articles/2017/11/08/11/47/mon-5pm-bp-guideline-aha-2017)). 90 matches the lowest NEWS2 systolic band, ≤90 ([NHS NEWS2 chart](https://www.nwas.nhs.uk/publications/news2-national-early-warning-score)) |
| Blood pressure, diastolic | 120 and above | below 60 or 90 and above | 120 matches the ACC/AHA crisis line; 90 is stage 2 hypertension ([ACC](https://acc.org/Latest-in-Cardiology/Articles/2017/11/08/11/47/mon-5pm-bp-guideline-aha-2017)) |
| Blood sugar (mg/dL) | below 70 or above 300 | below 80 or above 180 | Below 70 is level 1 hypoglycaemia in the ADA Standards of Care 2025 ([ADA](https://professional.diabetes.org/sites/dpro/files/2025-05/hypoglycemia-hcp-5-27-25.pdf)). 300 and 180 are product choices, not guideline values |
| Oxygen saturation (%) | below 92 | below 95 | Below 92 matches the lowest NEWS2 SpO2 scale 1 band, ≤91 ([NHS NEWS2 chart](https://www.nwas.nhs.uk/publications/news2-national-early-warning-score)) |
| Pulse (per minute) | below 50 or above 120 | below 60 or above 100 | Product choice inside the NEWS2 pulse bands (41–50 and 111–130 are both abnormal bands) ([NHS NEWS2 chart](https://www.nwas.nhs.uk/publications/news2-national-early-warning-score)) |
| Temperature (°F) | 102.2 and above (39 °C) | below 97 or above 99.4 | Close to the highest NEWS2 temperature band, ≥39.1 °C ([NHS NEWS2 chart](https://www.nwas.nhs.uk/publications/news2-national-early-warning-score)) |

Keywords such as a fall, chest pain, breathlessness, dizziness or unconsciousness (in English, Hinglish and Hindi script) are always red flags, whatever the readings.

**Family updates never add medical words.** If the AI's family update uses a medical word (for example "fracture", "infection", "fever") that the note does not mention in English or a common Hindi equivalent, the update is held. On the recorded 30-note run, this check fired on 0 of 30 summaries.
