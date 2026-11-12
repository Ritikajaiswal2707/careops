# How CareOps would plug into an agency's tools

Coordinators live in WhatsApp and spreadsheets, so CareOps has to fit there rather than add another screen to watch. This note sets out how each part would connect in a real pilot. None of it is built; the demo uses synthetic data and sends nothing.

| Today in the demo | In a pilot | Notes |
|---|---|---|
| Visits come from a synthetic CSV | **Import from the agency's schedule:** a Google Sheet or CSV export (visit, patient, nurse, date, slot, service) synced every 15 minutes | Most small agencies schedule in Sheets or Excel. Read-only access first; CareOps never edits the source sheet in phase 1 |
| Family messages are recorded examples | **WhatsApp Business Platform** (Cloud API) webhook delivers each incoming family message to `/api/analyze` | Needs a verified business number. Families must have opted in to receive messages from the agency |
| Message drafts are copied by hand | **Send from CareOps** after the coordinator approves, using pre-approved WhatsApp message templates (required for messages outside the 24-hour reply window) | Phase 1 keeps copy-and-paste: the coordinator stays the sender until trust is earned |
| Caregiver voice notes are typed | **Caregiver sends a WhatsApp voice note** to the agency number; the audio goes to `/api/visit-report/audio` (Whisper speech-to-text, then the report checks) | Audio is deleted after transcription; only the report is kept |
| Approvals live in the browser tab | **Audit log** in a database: who approved what, when, and what was sent | Needed before any automatic sending |
| Replacement nurses come from synthetic availability | **Nurses mark availability** in a simple weekly form or sheet | Same-day changes still come by phone; the coordinator records them |

## Data protection

Health information needs particular care. A pilot would follow India's Digital Personal Data Protection Act, 2023 and the DPDP Rules, 2025: clear consent from families for messages and voice notes, data kept only as long as needed, access limited to the agency's coordinators, and no patient data sent to an outside AI model without a data-processing agreement. The public demo avoids the question entirely by using synthetic data and keeping the live AI off.

## Phasing

1. **Read-only pilot (2 to 4 weeks):** Sheet import plus WhatsApp webhook; CareOps suggests and drafts, the coordinator copies and sends. Measure time to resolve a disrupted visit and how often drafts are sent unedited.
2. **Assisted sending:** approved drafts go out through WhatsApp templates from CareOps, with the audit log.
3. **Voice notes:** caregivers send voice notes straight to CareOps; held reports wait for the coordinator.
