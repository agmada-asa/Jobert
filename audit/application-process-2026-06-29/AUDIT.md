# Jobert application-process audit

Date: 2026-06-29  
Audit type: combined UX, accessibility, and implementation-state review  
Target: make preparing and completing a job application materially faster without submitting on the applicant's behalf

## Executive assessment

Jobert is currently a set of promising components, not an end-to-end application product.

- The scheduled job-discovery scraper is the most complete part.
- Telegram onboarding exists in code, but the final Notion setup step is broken.
- The answer-generation API and Chrome extension are proofs of concept.
- The `/apply` trigger, application review page, approve/edit loop, application persistence, and status updates described in the specification do not exist.
- The new extension takes the product toward the right execution surface, but it currently bypasses the specification's manual-first Phase 2 before that phase works.

The better product shape is one continuous flow: **discover job -> prepare in extension -> review/edit answers -> fill -> verify -> mark submitted**. Telegram should remain a notification and deep-link surface. Notion should be an optional import/export or archive, not the mandatory review UI.

## Evidence captured in this run

### Step 1 — Job discovery in Telegram

Health: **partly healthy**

The scheduled scraper fetches relevant Trackr roles, deduplicates them with `seen_jobs.json`, and sends Telegram messages containing an Apply link. This is the clearest working user value in the repository.

Blocker: no screenshot was captured because exercising the real Telegram bot would send messages to an external chat. The current request authorised analysis, not external messaging.

### Step 2 — First-time Telegram onboarding

Health: **blocked by implementation defect**

The bot asks for a Notion token, Notion parent page, PDF CV, and Gemini API key. It validates only token prefixes and PDF MIME type. The final step calls `create_kb_page`, but that function constructs a payload and never sends it or returns a result. The next line then calls `.get` on `None`, so onboarding cannot complete successfully as written.

UX risks:

- The applicant must collect and paste two developer credentials before receiving value.
- Setup spans Telegram, Notion settings, a Notion page, Google AI Studio, and back to Telegram.
- The bot says a token was “received” before checking whether it works.
- Setup is all-or-nothing; there is no visible progress recovery or resumable state.

Privacy/security risks:

- CVs are stored in a bucket that setup documentation instructs users to make public.
- Secrets are pasted into Telegram messages.
- Error responses can expose raw service error details to the user.

Blocker: no screenshot was captured because using the real onboarding would transmit credentials/files to external services.

### Step 3 — Connect the Chrome extension

Health: **visual shell works; authentication is a demo stub**

![Extension connection screen](01-extension-connect.png)

Strengths:

- The entry state is simple and has one obvious action.
- It fits a realistic side-panel width without clipping.
- The backend starts locally and its `/health` route returns `{"status":"healthy"}`.

UX risks:

- “Magic Code from Bot” gives no instruction for obtaining a code and no recovery path.
- Empty submission silently does nothing.
- Errors use blocking browser alerts.
- The UI does not explain what access is granted or how applicant data will be used.

Accessibility risks visible in this state:

- The text input has no persistent `<label>`; its placeholder is the only instruction.
- The primary blue `#007bff` with white text is approximately 3.98:1, below WCAG AA's 4.5:1 target for normal-sized text.
- The button is about 30px high, below the 44px WCAG 2.2 target-size recommendation.
- There is no authored focus-visible style.
- The document has no `lang` attribute.

Implementation state:

- Any user entering `123456` receives a hard-coded token and a hard-coded real Telegram user ID.
- The returned token is never checked by subsequent API endpoints.
- The API allows wildcard CORS while enabling credentials.

### Step 4 — Scan an application form

Health: **prototype only**

The content script scans `input`, `textarea`, and `select` elements and attempts to infer a label. This demonstrates the intended mechanism but is not reliable enough for a real application.

Key failure modes:

- Generated random IDs for fields without an ID/name cannot be resolved later during filling.
- Results from multiple frames are not combined; the side panel keeps only the frame with the most questions.
- Radio groups, checkboxes, fieldsets, custom comboboxes, contenteditable fields, and file uploads are not modelled correctly.
- The extension declares a narrow host list but injects its content script on `<all_urls>`.
- The specification promises job-description extraction, but the content script extracts only form controls.
- A scan reports “No questions found” after a fixed one-second timer, which is brittle on slow or multi-step forms.

Blocker: the in-app browser cannot execute this unpacked Chrome extension's privileged side-panel APIs, and there is no fixture or automated browser test in the repository from which to verify a real scan.

### Step 5 — Review generated answers

Health: **missing**

The side panel lists detected question labels and types, then exposes one “Generate & Fill Answers” button. There is no answer preview, per-answer edit, accept/reject control, source evidence, unsupported-field handling, or missing-information prompt. This removes the human review loop that the specification correctly prioritised.

Blocker: there is no implemented review screen to capture.

### Step 6 — Generate and fill

Health: **proof of concept with high correctness risk**

The backend downloads the public CV, reads a limited subset of first-level Notion blocks, prompts Gemini, parses free-form JSON, and returns an ID-to-answer map. The extension writes values and emits `input`, `change`, and `blur` events.

Key risks:

- The model call has no structured response schema or output validation.
- The job URL is supplied to the prompt, but the backend never fetches the job description.
- Job-page content and form questions are untrusted prompt input without defensive separation.
- If parsing fails, every field receives the literal string “Error generating answer”.
- Directly assigning `element.value` is unreliable for controlled React inputs and is incorrect for selects, radio buttons, and checkboxes.
- Filling reports success even if no field matched or no value persisted.
- Question labels are inserted into `innerHTML` without escaping.
- Required AI/PDF packages are installed in the current virtual environment but absent from the committed backend requirements, so a clean deployment will fail.

Blocker: a full generation run would use the user's stored CV, Notion token, and Gemini key against external services. It was not needed to establish the implementation gaps and was not performed.

### Step 7 — Verify, submit manually, and track status

Health: **missing**

There is no verification pass comparing requested answers with actual field values, no unresolved-field list, no review confirmation, and no manual-submission handoff. The `/applications` endpoint returns success but does not write to the database. The Notion application page, Approve/Needs Editing controls, Mark as Submitted control, `/status` command, and application history do not exist.

Blocker: there is no implemented screen or persisted state to capture.

## Current-state scorecard

| Capability | State | Evidence |
| --- | --- | --- |
| Scheduled discovery | Working foundation | Scraper and GitHub Actions workflow |
| Telegram onboarding | Implemented but broken at completion | `create_kb_page` never performs a request or returns |
| Secure account linking | Not implemented | Hard-coded code, token, and user ID |
| Profile/CV knowledge | Partial | Public CV URL plus shallow Notion block read |
| Form detection | Prototype | Generic DOM heuristics only |
| Answer generation | Prototype | Unvalidated free-form JSON from Gemini |
| Human answer review | Missing | Generate and fill are one action |
| Reliable form fill | Prototype | Text-like value assignment only |
| Application persistence | Stub | Endpoint returns success without a database write |
| Submission/status workflow | Missing | Exists only in specification |
| Automated tests | Missing | No backend, parser, extension, or end-to-end test suite |
| Deployability | Not reproducible | Committed requirements omit AI/PDF dependencies |

## What has been done well

- The specification made a sound early decision to prioritise answer quality and review speed over automatic submission.
- The scraper is intentionally small, cheap to run, and separated from the richer application workflow.
- User secrets are encrypted before database storage.
- The extension is a strategically better place than Notion for form-aware assistance.
- The system never attempts final submission in the current implementation, which avoids a dangerous false-confidence failure.

## The better way: one application spine

Use the browser extension as the active application workspace, with Telegram and Notion reduced to supporting roles.

1. **Discover** — Telegram sends the job link and an optional “Prepare with Jobert” deep link.
2. **Prepare** — The extension recognises a supported ATS and automatically scans the current step.
3. **Resolve** — Jobert shows detected fields, flags unsupported or missing information, and asks only the minimum follow-up questions.
4. **Review** — The applicant sees every generated answer before filling, can edit it, and can see which CV/profile fact supported it.
5. **Fill** — Jobert fills only accepted answers and uploads/selects nothing irreversible without explicit action.
6. **Verify** — A second scan confirms which values stuck and lists anything still incomplete.
7. **Finish** — The applicant submits manually; Jobert records the application only after confirmation.

Recommended role of each surface:

| Surface | Primary job |
| --- | --- |
| Telegram | Discovery notifications and lightweight status reminders |
| Extension | Scan, answer review, edit, fill, and verify |
| Backend | Authentication, encrypted profile storage, generation, and application records |
| Notion | Optional import/export or archive, not a runtime dependency |

This removes the current Telegram -> Notion -> job portal -> Telegram/Notion loop and keeps the applicant beside the form throughout.

## Recommended delivery sequence

### P0 — Prove one safe happy path

- Pick Greenhouse only.
- Replace demo auth with short-lived, single-use pairing codes bound to one user and one extension installation.
- Fix Notion page creation or, preferably, make Notion optional during onboarding.
- Move CV storage to a private bucket and use short-lived signed URLs or server-side reads.
- Add a real application write endpoint with ownership checks.
- Build a review state: detected question -> proposed answer -> edit/accept -> fill -> verified/unresolved.
- Never auto-submit.

### P1 — Make correctness measurable

- Define a typed field contract: stable locator, label, kind, options, required state, frame, and current value.
- Add Greenhouse fixture pages covering text, textarea, select, radio, checkbox, file, and validation states.
- Add parser unit tests, FastAPI tests, and one browser test for scan -> review -> fill -> verify.
- Use structured model output and reject missing, extra, or type-incompatible answers.
- Return explicit `filled`, `skipped`, `failed`, and `needs_user_input` results instead of a blanket success.

### P2 — Reduce applicant effort

- Replace developer-token-heavy onboarding with a small secure web onboarding flow.
- Import the CV once, extract a structured profile, and let users confirm facts.
- Ask for Gemini BYOK only if it remains a deliberate privacy/cost choice; explain the trade-off before requesting it.
- Add reusable answers for work authorisation, salary, location, notice period, and demographic opt-outs.

### P3 — Expand carefully

- Add Lever as a second tested adapter.
- Keep a generic parser only as a clearly labelled fallback.
- Add Workday after multi-step state, custom controls, account/login boundaries, and recovery are tested.
- Keep Notion sync optional and asynchronous so Notion failures never block an application.

## Evidence limits

- The only currently capturable user-facing state was the extension connection screen.
- Telegram, Notion, Supabase, Gemini, and real ATS flows were not exercised with user data or external writes.
- Screenshot evidence can identify visible accessibility risks but cannot establish keyboard behavior, screen-reader output, zoom resilience, or full WCAG conformance.
- Static and runtime inspection establishes that the local API starts and that demo endpoints respond; it does not establish production readiness.
