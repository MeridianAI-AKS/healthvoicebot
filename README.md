# Hindustan Wellness — Multilingual Help Desk Agent (Prototype)

An inbound customer help-desk agent for Hindustan Wellness that answers
enquiries in Indian languages, over text or voice. Built for a
Microsoft-introduced customer demo.

Reference implementations: `fixfeels_backend` / `fixfeels_frontend` (FastAPI +
React + Azure OpenAI + Azure Speech). Those run an *outbound scripted sales
call*; this is an *inbound help desk*, so the speech and transport plumbing
carried over and the conversation control flow was rebuilt.

| Phase | Scope | State |
|---|---|---|
| 1 | Knowledge base — scrape and structure the catalogue | done |
| 2 | Backend — retrieval, multilingual prompt, tool loop | done |
| 3 | Frontend — chat transcript, language picker, voice | done |
| 4 | Mock operations tools, safety layer, escalation | done |

## Quick start

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # fill in Azure OpenAI + Speech
python scrape_hw_knowledge.py # already run; regenerates data/hw_knowledge.json
python build_index.py         # optional — semantic search
python -m uvicorn main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Without Azure credentials the backend still starts, `/api/health` reports what
is missing, the UI shows a degraded banner, retrieval works on keyword search
and the safety gate works. Only model replies and voice need keys.

```bash
cd backend && python test_agent.py    # 31 offline checks, no credentials needed
cd backend && python retrieval.py     # retrieval smoke queries
```

## How a turn works

```
customer message
   │
   ├─ emergency gate ─────────────► localised "call 112" reply, stop
   │   (regex, before the model, in 6 languages)
   │
   ├─ language detection (script, then romanised-Hindi cues)
   │
   ├─ system prompt: persona + safety rules + detected language + known facts
   │
   ├─ tool loop (max 4 rounds)
   │     search_catalogue ....... real, over the 700-package corpus
   │     get_package_details .... real
   │     check_pincode .......... mock
   │     get_available_slots .... mock
   │     lookup_booking ......... mock
   │     get_report_status ...... mock
   │     create_booking ......... mock, in-memory
   │     escalate_to_human ...... mock
   │
   └─ NDJSON stream: meta → tool… → delta → done
```

Every factual claim has to come back from a tool — the prompt forbids quoting a
price, turnaround, coverage or booking state from model memory.

### Retrieval

The corpus is 3.2 MB across 2,373 documents, far too large for the
prompt-stuffing the reference uses. Search is BM25 with two corrections that
mattered in testing: a title-overlap boost and per-kind weighting, because plain
BM25 ranked two-line taxonomy stubs above the package the customer asked for.
Light English suffix stemming lets "fast" match "fasting"; it is skipped for
non-ASCII tokens so Indic words are not mangled.

Embeddings are optional. When `build_index.py` has been run, keyword and vector
rankings are combined by reciprocal rank fusion. Cross-language recall works
even without embeddings because the model issues its `search_catalogue` query in
English regardless of the customer's language.

### Languages

Six for the demo: Hindi, Indian English, Bengali, Tamil, Telugu, Marathi.

Azure constraints that shaped this (verified against Microsoft Learn):

- Continuous language identification accepts **at most 10** candidate locales;
  accuracy drops as candidates are added, so the set is deliberately small.
- LID **cannot switch language mid-sentence**. Code-mixed Hinglish resolves to
  whichever language dominates, so Hindi leads the candidate list and the model
  is told to mirror whatever mix the customer used rather than "correct" it.
- **Bengali has speech-to-text but no Azure neural voice.** It is offered as
  text-only; `/api/languages` marks it `speakable: false` and the UI hides the
  listen control instead of reading Bengali with an English voice.

### Safety

The reference guards scope only. In a diagnostics context that is not enough,
so this build adds:

- an **emergency gate** that runs before the model and cannot be talked around,
  answering in the customer's own language;
- a **no-interpretation rule** — the agent will not read a lab value, call a
  result normal, name a condition or discuss medication, and instead offers the
  free doctor consultation that already comes with every report;
- symptom answers framed as *what Hindustan Wellness lists*, drawn from the
  company's own symptom→test mapping, never as clinical advice.

Transcripts stay in memory. Nothing is written to disk — the reference's habit
of appending every turn to a local `qa_log.json` would be patient data here.

## Phase 1 — knowledge base

`hindustanwellness.com` is an Angular SPA that renders nothing server-side, so
the reference's HTML scraping returns an empty `<app-root>`. The site instead
calls a public JSON catalogue API; endpoint names and payload shapes were read
out of its own bundle (`main.*.js`) and wrapped in `hw_api.py`.

**Deliberately not touched:** account, booking, prescription, wishlist and
payment endpoints on the same hosts. They carry customer PII.

| Endpoint | Gives |
|---|---|
| `sectionWebDetails` | Tests by condition / habit / symptom |
| `getHealthCategoryPackage` | Package categories |
| `getHealthCatalogueData` | Packages within a category |
| `getSortingOrderData?pageNo=&catalogueType=all` | Full catalogue, 20/page |
| `getAllCatalogueDetails` | Detail, prep instructions, FAQs, test breakdown |
| `getPackageTests` | Packages for a symptom/condition |

### What the crawl produced

| | |
|---|---|
| Packages | 700 (0 failures) |
| With test breakdown | 660 — the other 40 are single tests, not panels |
| With package FAQs | 442 |
| Distinct tests named | 1,218 |
| Price range | ₹80 – ₹31,200 |
| Taxonomy | 8 conditions, 7 habits, 136 symptoms |
| Symptom → package links | 647 |
| Output | `backend/data/hw_knowledge.json`, 3.2 MB |

Company facts that exist only in the rendered marketing pages — hours, phones,
offices, lab credentials, doctors, the 7 site FAQs — are in `site_facts.py`,
dated and separate from API-sourced data.

`--enrich` re-runs only the taxonomy pass against an existing corpus instead of
re-crawling all 700 detail calls.

## Demo script

1. **Price** — "What does a full body checkup cost?" → real catalogue answer.
2. **Language switch** — ask the same in हिन्दी, then বাংলা. The reply language
   follows the question; the Bengali turn shows the text-only badge.
3. **Symptom** — "I have hair loss, which test?" → thyroid, ferritin, iron, from
   the company's own mapping.
4. **Operational** — "Check my booking, my number is 9800000002" → demo booking,
   report ready. Chips mark it as demo data.
5. **Booking** — check pincode 110092, list slots, create a booking.
6. **Safety** — "My haemoglobin is 9.2, is that bad?" → declines to interpret,
   offers the free doctor consultation.
7. **Emergency** — "I am having chest pain" → immediate 112 deflection, no
   booking attempted, in the caller's language.

## Known limitations

- **Sessions are in memory.** They die on restart and are not shared across App
  Service instances. Redis or Table Storage before any real traffic.
- **Operational tools are fixtures.** Bookings, reports, slots and pincode
  coverage come from `data/mock_operations.json`. Every such result carries
  `"source": "mock"` and the UI badges it.
- **Replies are not token-streamed.** The model answers in the same call that
  stops requesting tools, so the reply arrives as one delta. The NDJSON envelope
  is unchanged, so real streaming can be added without touching the client.
- **Not load-tested**, and no live Azure verification has been done — see below.

## What has and has not been verified

**Verified running:**

- 31 offline pipeline checks with a stubbed model (`python test_agent.py`).
- Retrieval smoke queries and 8 language-detection cases.
- Backend serving `/api/health`, `/api/languages`, `/api/session/start` and
  `/api/chat/stream`; greetings render correctly in all six scripts.
- The full UI in a browser against the live backend: session start, message
  send, the emergency guardrail with its styling and badge, automatic language
  switching, and the degraded-mode banner.
- Production build: 157 kB initial bundle, Speech SDK (381 kB) lazy-loaded on
  first mic use.

**Not verified — no Azure credentials were available:** real model replies and
their quality, tool calling against the live API, embeddings and hybrid ranking,
TTS voices, and browser microphone capture with language identification. These
are the first things to exercise once keys are in `backend/.env`.

## Facts to confirm with the client

Flagged in code, because the agent would state them to customers:

- **Support hours** — the contact page reads "5a.m. to 12p.m. (Mon-Sat)".
  Midday or midnight?
- **City coverage** — home page says "50+ Cities", About page says "28 cities,
  35+ districts".
- **Pincode serviceability** — the site's `pincodes` endpoint rejects the payload
  shape its bundle implies. Needs the correct shape or a coverage list.
