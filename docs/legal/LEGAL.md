# Legal and compliance guide

> **This is not legal advice.** It is an engineering summary of the licensing and
> compliance points identified in this codebase, written to prepare a review by a
> qualified lawyer in the jurisdictions where you will operate. Items marked
> **DECISION** need the project owner; items marked **LAWYER** need legal review
> before a public launch.

Status legend: ✅ done in the code/repo · 🟡 partially done · ⬜ open

## Summary

| # | Topic | Status |
|---|---|---|
| 1 | License for this project's own code | ⬜ **DECISION**: no LICENSE file yet, so the code is "all rights reserved" by default |
| 2 | KiCad (GPL-3.0-or-later) | 🟡 used as a separate program; recommendation for the 3 KiCad scripts below |
| 3 | KiCad libraries (CC BY-SA 4.0 + design exception) | ✅ attribution in app and exports; designs are not ShareAlike |
| 4 | Open-source dependencies | ✅ inventory generated; only weak copyleft (LGPL/MPL), used unmodified |
| 5 | Container images | 🟡 obligations apply only if you *distribute* images; Redis license note |
| 6 | AI assistant (Anthropic API) | 🟡 server-side key, disclosure in UI; terms acceptance and privacy are on you |
| 7 | Product liability / engineering disclaimer | ✅ disclaimer in UI and every export; ⬜ **LAWYER**: Terms of Service |
| 8 | Privacy / data protection | ⬜ **LAWYER**: privacy policy, DPA, retention |
| 9 | AI-specific regulation | ⬜ **LAWYER**: e.g. EU AI Act transparency duties |
| 10 | Trademarks and branding | 🟡 non-affiliation notice; ⬜ name clearance |
| 11 | Export control / sanctions | ⬜ **LAWYER** if selling internationally |

---

## 1. License for this project's own code — DECISION

There is currently no `LICENSE` file. Without one, nobody else has permission to use,
copy or modify the code. Choose one before sharing the repository or accepting
contributions:

| Option | When it fits | Consequence |
|---|---|---|
| **Proprietary** (closed source, SaaS) | You sell access to a hosted service | Keep the repo private. KiCad's GPL does not force you to publish your code as long as KiCad is only *run* on your servers (§2). |
| **GPL-3.0-or-later** | You want an open-source project aligned with KiCad | Simplest compatibility story; others may self-host and must share modifications they distribute. |
| **AGPL-3.0** | Open source, but competitors hosting it must publish changes | Strong copyleft also over the network. |
| **MIT / Apache-2.0** | Maximum adoption, permissive | Allowed for the parts that do not import KiCad (see the scripts note below). |

**KiCad scripts.** `backend/app/kicad/scripts/build_pcb.py`, `drc_pcbnew.py` and
`probe.py` run inside KiCad's Python and `import pcbnew` (GPL). The Free Software
Foundation's position is that code importing a GPL module forms a combined work. The
cautious approach, whatever you choose for the rest, is to license **these three files
under GPL-3.0-or-later**. The rest of the backend talks to them only through command
lines and files, in a separate process (an "arm's length" boundary that the code
keeps on purpose: `app/kicad/runner.py` only executes those scripts and `kicad-cli`).
Confirm this structure with your lawyer.

## 2. KiCad (GPL-3.0-or-later)

- ✅ KiCad is invoked as a separate program (`kicad-cli`, KiCad's Python) through
  subprocesses or the official container. No KiCad source is copied into this repo.
- ✅ Credited in the app ("Legal & notices") and in `THIRD_PARTY_NOTICES.md`.
- **Running a hosted service** (users only reach it in a browser): the GPL has no
  network clause, so there is no source-sharing duty for KiCad or for your code.
- **Distributing** KiCad, for example publishing the backend Docker image, which is
  built on `kicad/kicad:9.0`, or shipping it to customers for self-hosting: you must
  comply with the GPL for the KiCad binaries. In practice you provide the corresponding
  source of the exact KiCad version (and the Debian packages in the image), for example
  through a written offer or a reliable link to the matching upstream source, plus the
  license texts. ⬜ Set this up before you publish images.

## 3. KiCad symbol and footprint libraries

License: CC BY-SA 4.0 with an exception for designs (verbatim text in
`THIRD_PARTY_NOTICES.md`; confirmed from the license shipped with the installed
libraries).

- ✅ **User designs are free of ShareAlike.** Schematics, boards, Gerbers and BOMs
  that use the libraries fall under the exception. Users own their designs.
- ✅ **Showing library graphics in the browser** shares the library data itself, which
  requires attribution and the license. Done in the "Legal & notices" dialog, in
  `GET /api/legal`, and in `NOTICE.txt` inside every exported project ZIP.
- If you ever modify the libraries and redistribute them (for example a curated
  library download), that modified library must stay CC BY-SA 4.0.
- ✅ The libraries are not committed to this repository (`backend/data/` is git-ignored).

## 4. Open-source dependencies

- ✅ `docs/legal/DEPENDENCY_LICENSES.md` lists all runtime packages (49 Python, 86 npm)
  with declared licenses. Regenerate it with `scripts/third_party_licenses.py` whenever
  dependencies change.
- Everything is permissive except weak-copyleft libraries used unmodified:
  `psycopg` (LGPL-3.0), `certifi` (MPL-2.0), `sharp`'s libvips binaries (LGPL-3.0).
  This is compatible with proprietary use if you don't modify them and keep their
  license notices when distributing.
- No GPL or AGPL packages are among the runtime dependencies.
- Dev-only tools (pytest, ruff, eslint, playwright, vitest) are not shipped.
- ⚠ ESLint 9 is end-of-life upstream; that's a maintenance issue, not a licensing one.

## 5. Container images

- Obligations only arise when you distribute images. Running them yourself is fine.
- `kicad/kicad:9.0`: see §2.
- `redis:7-alpine`: Redis **7.4 and later** use source-available terms (RSALv2 /
  SSPLv1) instead of BSD. Using Redis as an internal queue inside your product is
  allowed; offering Redis itself as a hosted service is not. If you prefer a fully open
  license, switch to **Valkey** (BSD-3-Clause), which is protocol-compatible
  (`image: valkey/valkey:8-alpine` in `docker-compose.yml`). ⬜ **DECISION**
- `postgres:16-alpine` (PostgreSQL License, permissive) and `node` (MIT and others):
  no concerns.

## 6. AI assistant: how it works and what is legally needed

**How it is implemented:** through the **official Anthropic API**, nothing else.

- The backend uses the official `anthropic` Python SDK (MIT) to call the Messages API
  (`backend/app/ai/claude.py`). Model `claude-opus-5-5` by default (configurable with
  `ANTHROPIC_MODEL`).
- The API key is read from the backend environment (`ANTHROPIC_API_KEY`) and is never
  sent to the browser; the frontend only talks to the backend.
- The model can only call 7 backend functions (read design, search parts, read
  validation reports, propose changes, ask questions). It cannot run commands, and
  nothing changes without the user clicking **Apply**.

**What you need to do:**

- ✅ Server-side key; users never see it.
- ⬜ **Accept Anthropic's Commercial Terms of Service and Usage Policy** when you create
  the API key (Anthropic Console). You, as the operator, are the Anthropic customer and
  are responsible for how your users use the feature; your own Terms should forbid uses
  that the Usage Policy prohibits.
- ✅ **Disclosure:** the AI panel and the "Legal & notices" dialog say the assistant is
  an AI (Claude by Anthropic), that messages, design data and check results are sent to
  Anthropic, and that the output can be wrong.
- ⬜ **Data protection:** Anthropic processes the data you send on your behalf. Review
  Anthropic's commercial privacy terms and data retention, and put a Data Processing
  Agreement (DPA) in place with Anthropic if you process personal data of EU/UK users.
  List Anthropic as a sub-processor in your privacy policy.
- ⬜ **Costs:** usage is billed per token to your Anthropic account. Set spend limits
  in the Anthropic Console; consider rate-limiting the chat endpoint per user once
  authentication exists.
- Note: the server-side refusal fallback (`ANTHROPIC_ENABLE_FALLBACKS=true`) is a beta
  API feature; set it to `false` if your policies exclude beta features.
- AI output (proposals, explanations) is not legal or engineering certification;
  covered by the disclaimer in §7.

## 7. Product liability and the engineering disclaimer

PCBs can cause fire, electric shock or radio interference. The platform must not be
presented as guaranteeing correctness.

- ✅ Validation levels never claim more than KiCad checked; "Engineering verified" is
  never set automatically.
- ✅ No-warranty and engineering-responsibility disclaimer: dashboard footer, editor
  status bar ("Legal & notices"), `GET /api/legal`, and `NOTICE.txt` in every exported
  project, which also records which checks passed at export time.
- ✅ Templates list their assumptions and state that they are not verified designs.
- ⬜ **LAWYER:** a Terms of Service / EULA with warranty disclaimer and limitation of
  liability enforceable in your jurisdiction (consumer-protection law can limit
  disclaimers, for example in the EU), an acceptable-use policy, and a statement that
  users own their designs.
- ⬜ Do not market compliance (CE, FCC, UL, IPC) unless it is actually verified.

## 8. Privacy and data protection

Current state: there are no user accounts, so the platform stores project data
(designs, AI chat messages, check reports, generated files) but no identity data. That
changes once authentication is added.

- ✅ Deleting a project deletes its revisions, jobs, check results, AI messages and
  stored files (database cascades plus storage cleanup).
- ✅ No analytics or tracking scripts; the only external service is Anthropic (opt-in
  through the API key). Datasheet links open the manufacturer's site in a new tab.
- ⬜ **LAWYER:** privacy policy (what is stored, where, for how long, sub-processors
  such as Anthropic and the hosting provider), legal basis, data subject rights,
  retention periods for job logs and artifacts, and cookie notice if cookies are added.
- ⬜ When adding accounts: GDPR/UK GDPR/CCPA obligations, data export, account
  deletion, breach procedures.

## 9. AI-specific regulation

- ⬜ **LAWYER:** check transparency obligations for AI systems that interact with
  people, for example Article 50 of the EU AI Act (applicable from August 2026). The UI
  disclosure in §6 is designed to support this, but applicability and wording should be
  confirmed. A design assistant like this one is not expected to be a "high-risk" use,
  but confirm it for your customers' sectors.

## 10. Trademarks and branding

- ✅ Notice: "KiCad is a trademark of the KiCad project; Claude and Anthropic are
  trademarks of Anthropic, PBC. This product is not affiliated with or endorsed by
  either." Shown in the app and in exports.
- ✅ The product does not reuse Flux.ai's name, logo or branding; "inspired by"
  products should not be named in marketing without care.
- ⬜ **DECISION/LAWYER:** "PCB AI" is a descriptive working name. Run a trademark
  clearance search before using it commercially.
- Component names (NE555, AMS1117, 2N7002) are used descriptively, which is fine.

## 11. Export control and sanctions

- ⬜ **LAWYER** if you sell internationally: general-purpose EDA software is usually
  low-risk, but check export rules and sanctions screening for your customers, and that
  Anthropic's API is offered in the countries where you operate.

---

## What was changed in the code for compliance

- `backend/app/legal.py`: single source for disclaimer, AI disclosure, library notice,
  attributions and non-affiliation text.
- `GET /api/legal`: returns those texts (used by the UI).
- Export ZIP now contains `NOTICE.txt` (disclaimer, attribution, checks at export time).
- UI: "Legal & notices" dialog (dashboard footer, editor status bar); AI panel
  disclosure that data is sent to Anthropic.
- `THIRD_PARTY_NOTICES.md`, `docs/legal/DEPENDENCY_LICENSES.md`,
  `scripts/third_party_licenses.py`.
- Tests: `test_legal_endpoint`; the export test asserts `NOTICE.txt` contents.
