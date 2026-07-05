# Requirements Interview — AU Insurance Claims Phone Intake Agent

Source: live stakeholder interview (no formal PRD exists). Conducted per
cxas-agent-foundry `references/interview-guide.md` Round 1.

## 1. Agent purpose

An AI phone agent for an Australian general insurance company. It answers
inbound calls from policyholders who want to lodge a new claim (First Notice
of Loss / FNOL). The agent's ONLY job this version: capture the incident
details a human claims consultant needs, then email that captured
information to a nominated mailbox for offline processing. It does NOT:
- make any coverage/eligibility decision
- confirm the claim is accepted, approved, or will be paid
- quote or discuss settlement/payout amounts
- give legal or medical advice
- verify the caller's identity (identity/ownership verification happens
  offline, after the email is received, by a human)

## 2. Modality

- Channel: phone / voice, via Google Telephony Platform (GTP), attached
  directly to the CX Agent Studio (CES) app.
- Model: voice modality, so per platform guidance this should use
  `gemini-3.1-flash-live`.
- Speaking rate / voice persona: stakeholder confirmed default platform
  pacing and voice are acceptable for this build; no custom speaking rate.
- Language: English only at launch. No multilingual requirement for this
  version.

## 3. Region / data residency

- CES region: `us` multi-region.
- Stakeholder has explicit internal approval to use US-region cloud
  resources for this workload, including for eventual production use, not
  just prototyping. (Note for TDD: CES currently supports only `us` and `eu`
  regions — no Australia region exists. This is a known, accepted tradeoff,
  not an open question.)
- No existing GCP project should be reused. A prior local `gcloud` config
  pointed at a project called `claims-lodgement-20260628` — stakeholder
  confirmed this is unrelated/stale and a fresh project should be created.

## 4. Intents in scope

- Single in-scope intent: caller wants to lodge/report a new insurance
  claim (FNOL).
- All other intents are explicitly OUT of scope for this agent, including:
  - checking the status of an existing claim
  - a direct request to "speak to a person" / human agent
  - any other general inquiry
  - For all of the above: the agent should politely decline, explain it can
    only take new claim notifications right now, and redirect the caller to
    another contact channel (e.g. the insurer's main claims line). It does
    NOT attempt a live transfer/handoff for these cases.

## 5. Emergency handling (hard requirement, not optional)

If at any point the caller's language indicates an active emergency or
danger in progress (e.g. fire currently burning, someone injured right now,
an ongoing dangerous situation), the agent must immediately stop normal FNOL
intake and instruct the caller to hang up and call 000 (Australian emergency
number). This takes priority over completing the data-capture flow.

## 6. Data fields to capture (FNOL, generic personal lines — no existing
   reference form; designed from scratch per stakeholder decision)

No existing claim form/schema was provided — the stakeholder explicitly
chose to have this field list designed from scratch rather than mirroring
an existing system. Proposed fields (subject to TDD review):

- Caller's full name
- Best contact phone number for a callback
- Policy number, if known (caller may not know it — must be optional, agent
  should not block progress if caller doesn't have it)
- Date and (approximate) time the incident occurred
- Location of the incident
- Open-text description of what happened / the loss or damage
- Whether anyone was injured (flag only — used to trigger the emergency
  guardrail if injury is described as current/ongoing; not for collecting
  medical detail)
- Whether there is any immediate hazard/urgent risk (flag — also ties to
  the emergency guardrail)
- Optional: preferred callback time/window

The agent should read back the captured details to the caller for
confirmation before submitting (no visual confirmation is possible on a
voice call).

## 7. Tools / backend integration

- No existing backend claims system, policy admin system, or API exists to
  integrate with. Explicitly confirmed: "none, the agent will capture via
  email and send to mailbox."
- Exactly one tool is needed: a wrapper tool (proposed name
  `submit_claim_notification`) that, once all required fields are captured
  and confirmed, formats the data and sends a single email via the Gmail
  API to a nominated address (michael@michael-lo.com).
- On failure to send (e.g. Gmail API error), the agent should apologize to
  the caller, avoid silently ending the call, and offer a fallback such as
  taking a callback number so a human can follow up — not leave the caller
  with no acknowledgement that submission failed.

## 8. Auth / identity verification flow

None. Explicitly confirmed twice: "no verification, we accept it as is,
after its sent to the email, then we verify (offline)." The call is fully
unauthenticated. Anti-abuse/fraud screening is accepted as an out-of-scope
risk for this prototype (owned by the offline verification step, not by
this agent).

## 9. Guardrails required

- Hard rule: redirect active emergencies to 000 (see section 5) — highest
  priority, overrides normal flow.
- No coverage/eligibility opinions, no payout/settlement figures, no
  claim-acceptance-or-denial language.
- No legal or medical advice.
- Must not collect payment/banking details on this call (out of scope for
  FNOL intake; collecting this would be a fraud-surface expansion the
  stakeholder has not asked for).
- Standard defense-in-depth expected per platform Design Guide: prompt-
  injection guard, safety filters, and explicit behavioral Rules layered
  with the above.

## 11. Round 2 — resolved TDD open questions

Following the initial TDD draft, the stakeholder resolved these open
questions:

- **Field-collection implementation pattern:** confirmed — use the
  platform's **Slot-Filling Framework** (deterministic, code/tool-visibility
  driven state), not a simple instruction-driven taskflow. This applies to
  all fields listed in section 6.
- **Emergency + submission-outcome determinism:** confirmed — build the
  proposed `flag_emergency` tool plus `before_model_callback` (deterministic
  hang-up-and-call-000 redirect) and `after_model_callback` (guarantee the
  agent speaks a success/failure acknowledgment before `end_session`) as
  designed in the draft TDD. This is the correct way to satisfy the
  already-mandatory hard requirements in sections 5 and 7 — not a new
  requirement, just confirmation of the deterministic-callback approach.
- **Gmail API authentication:** `michael@michael-lo.com` is a **Google
  Workspace-managed domain**. `submit_claim_notification` should
  authenticate via a **service account with domain-wide delegation**
  (no interactive login required — appropriate for an unattended phone-line
  tool), rather than an OAuth2 user-consent flow.
- **Out-of-scope redirect script:** exact wording confirmed — the agent
  must state: *"This phone number is only for express claim lodgements;
  please call CGU general enquiries on 1800 248 224."* Use this verbatim
  (adapting only for grammatical fit within the turn) for every out-of-scope
  case in section 4 (existing-claim status check, request to speak to a
  person, any other general inquiry).
- **Retry limit on a required field:** confirmed — retry up to **2**
  additional times (3 total attempts) if the caller can't or won't provide
  a required field, then proceed without it, marking that field as "not
  captured" in the submitted email, rather than blocking the call
  indefinitely.
- **Priority ordering, emergency vs. out-of-scope:** confirmed — the
  emergency override always takes priority if both could apply to the same
  utterance (not expected to co-occur in practice, but ruled on for
  completeness).
- **Telephony session parameters (GTP-supplied ANI/caller metadata):** not
  yet resolved — deferred to implementation time when the GTP channel is
  actually configured; not a blocker for TDD approval. Current design
  assumption stands: the callback phone number is always captured verbally
  as a field, not assumed to be auto-populated by the platform.

## 10. Known constraints / accepted tradeoffs (carry into TDD "Known Issues")

- No Australia region available on CES; `us` region accepted by
  stakeholder for prototype and production.
- No identity verification on the call — accepted; verification is a
  downstream, offline, human step.
- No backend system of record — the email IS the system of record hand-off
  for this version. Single point of failure if the email send fails (see
  section 7 fallback behavior).
- English only; no multilingual support this version.

## 12. Round 3 — resolved during TDD review (post-draft-2)

- **GCP project (reverses §3):** stakeholder now confirms the agent should
  be built in the **existing** project `claims-lodgement-20260628`, under
  gcloud account `michael.solo@mcosolutions.com.au` — NOT a fresh project
  as §3 originally stated. §3's "stale/unrelated" framing no longer applies;
  supersede it. **Superseded again, same day (see §13):** the final GCP
  project is `graphic-tide-501406-p2` (org `mcosolutions.com.au`), not
  `claims-lodgement-20260628` — see §13 for why.
- **GTP telephony session parameters (resolves §11's deferred item):**
  investigated directly against Google Telephony Platform docs — GTP
  auto-populates a session parameter `telephony-caller-id` (type `Text`)
  with the caller's ANI on every call; no other metadata (call SID, custom
  headers) is auto-supplied absent custom SBC/SIP configuration, which is
  out of scope. Design implication: `callback_phone` should be pre-filled
  from `telephony-caller-id` when present, with the agent reading it back
  for confirmation rather than asking cold; falls back to asking verbally
  if the parameter is empty/absent.
- **Welcome / greeting message (new requirement):** the hotline currently
  has no greeting specified. Stakeholder wants the agent to open every call
  with a named persona, "Amanda," using (adapted only for grammatical fit):
  *"Good day, you've reached CGU express claim lodgements, my name is
  Amanda, how can I help you?"*
- **Submission architecture redesign (supersedes §7's single-tool design):**
  stakeholder wants `submit_claim_notification` to be non-blocking for the
  call, and wants claim data to survive a Gmail outage rather than being
  lost if the send fails. Confirmed redesign:
  1. Synchronous, fast: the tool writes the full claim record to a
     **Firestore** collection — this durable write is the only operation
     the live call waits on, and is the new source of truth / success
     criterion for ending the call gracefully.
  2. Decoupled, async: the tool enqueues a **Cloud Task** that triggers a
     separate Cloud Function to send the Gmail email after the call has
     already ended. Gmail failures no longer block or need to surface to
     the caller — the record's durability no longer depends on Gmail.
  `after_model_callback`'s acknowledgment/fallback logic now gates on the
  Firestore write's success/failure, not Gmail's. Firestore write failure
  (rare) becomes the new caller-facing failure-fallback trigger (apologize,
  take a callback number) — this replaces the old "Gmail send failure"
  fallback trigger from §7/§11.

## 13. Project correction (same day as Round 3, post-TDD-update)

- **Final GCP project (supersedes §12's `claims-lodgement-20260628`):**
  while reviewing environment setup, an existing, already-deployed
  `fnol-claims-agent` app was discovered in `claims-lodgement-20260628`
  (a separate, unrelated prior build — different tool/model choices,
  `gemini-2-flash` vs. this TDD's `gemini-3.1-flash-live`). Stakeholder
  confirmed: ignore that prior agent, and use a **different** GCP project
  for this build — `graphic-tide-501406-p2`, org `mcosolutions.com.au`.
  This is now the confirmed target project for scaffolding, infra
  (Firestore, Cloud Tasks, Cloud Function, GCS bucket), and deployment —
  `claims-lodgement-20260628` is no longer relevant to this build at all.
- **App name (new):** `insurance_claims`.
- **GCS bucket for audio evals:** create a new bucket for this project;
  stakeholder asked for best-practice IaC (Terraform) so the setup is
  reproducible by others, since the repo is public
  (github.com/michaelsolo221/insurance_claims).
