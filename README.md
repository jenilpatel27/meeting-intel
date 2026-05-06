# 🧠 Meeting Intelligence System

An AI-powered web application that transforms client meeting transcripts into
structured project scopes, sprint plans, and Jira issues — with a human
approval gate at every stage.

> Upload transcript → AI extracts requirements → clarification loop →
> Scope of Work → sprint plan → push to Jira. Nothing moves forward without
> explicit user approval.

---

## 📸 What it does

| Stage | What happens |
|-------|-------------|
| 1 · Parse | AI reads the transcript and extracts modules, requirements, integrations, constraints, assumptions, and unknowns |
| 2 · Clarify | AI generates targeted questions from gaps. User answers, skips, or asks their own questions |
| 3 · Scope of Work | AI writes a full SoW in markdown. User gives feedback, AI revises with a changelog |
| 4 · Sprint Plan | AI breaks the SoW into Fibonacci-pointed tasks organized into 2-week sprints |
| 5 · Jira Sync | Epics, Issues, and Sprints pushed to Jira in three confirmed batches |

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Streamlit | Browser UI in pure Python — no HTML/JS needed |
| Backend | FastAPI + Uvicorn | REST API, async-ready, auto-docs at /docs |
| AI / LLM | LangChain + Google Gemini | Prompt management, JSON parsing, retry logic |
| Storage | SQLite | Zero-config local persistence — one .db file |
| Jira | Jira REST API v3 + Agile API | Epics, Stories, Sprints via HTTP |

---

## 📁 Folder Structure

meeting-intel/
│
├── .env                        ← Your secrets (never committed)
├── .env.example                ← Template for others
├── .gitignore
├── requirements.txt
├── README.md
│
├── backend/
│   ├── main.py                 ← FastAPI app + all API routes
│   ├── models.py               ← Pydantic data models
│   ├── database.py             ← SQLite read/write helpers
│   │
│   ├── pipeline/
│   │   ├── stage1_parse.py     ← Transcript extraction
│   │   ├── stage2_clarify.py   ← Question generation + processing
│   │   ├── stage3_sow.py       ← Scope of Work generation + revision
│   │   ├── stage4_sprint.py    ← Task + sprint plan generation
│   │   └── stage5_jira.py      ← Jira push orchestration
│   │
│   └── services/
│       ├── llm.py              ← LangChain + Gemini setup, retry logic
│       └── jira_client.py      ← Jira REST API wrapper
│
├── frontend/
│   └── app.py                  ← Complete Streamlit UI (all 5 stages)
│
└── data/
└── projects.db             ← Auto-created SQLite database

---

## ⚙️ Setup Instructions

### Prerequisites

- [Anaconda](https://www.anaconda.com/download) installed
- A free [Google AI Studio](https://aistudio.google.com) account (for Gemini API key)
- A free [Atlassian Jira](https://www.atlassian.com/software/jira) account
- [Git](https://git-scm.com/download/win) installed

---

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/meeting-intel.git
cd meeting-intel
```

### 2. Create and activate conda environment

```bash
conda create -n meeting-intel python=3.11
conda activate meeting-intel
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

GOOGLE_API_KEY=your_gemini_key
JIRA_DOMAIN=yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your_jira_token
JIRA_PROJECT_KEY=MIS

**Getting your Gemini API key:**
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click Get API Key → Create API Key
3. Copy and paste into `.env`

---

### 5. Run the application

You need **two terminals** open simultaneously.

**Terminal 1 — Start the backend:**
```bash
conda activate meeting-intel
cd path/to/meeting-intel
uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Start the frontend:**
```bash
conda activate meeting-intel
cd path/to/meeting-intel
streamlit run frontend/app.py
```

Open your browser at: **http://localhost:8501**

Verify the backend is running: **http://localhost:8000/health**

---

## 🔧 Jira Configuration

### Step 1 — Create a Classic Scrum project in Jira

1. Log into your Jira account
2. Go to Projects → Create project
3. Select **Scrum** → Choose **Company-managed** (not Team-managed)
4. Note your **Project Key** (e.g. `MIS`)

> ⚠️ Must be a Company-managed (classic) project. Team-managed projects
> do not support the Agile Sprint API or Epic Link custom fields.

### Step 2 — Get your API token

1. Go to [id.atlassian.com/manage-api-tokens](https://id.atlassian.com/manage-api-tokens)
2. Click **Create API token**
3. Give it a name (e.g. `meeting-intel`)
4. **Copy it immediately** — you cannot view it again

### Step 3 — Add to `.env`

JIRA_DOMAIN=yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=paste_token_here
JIRA_PROJECT_KEY=MIS

### Step 4 — Test in the app

In Stage 5 of the app, click **Test Connection**.
You should see: `✅ Connected as: Your Name`

---

## 🎯 How Each Stage Works

### Stage 1 — Transcript Parsing
The transcript is sent to Gemini with a structured prompt requesting JSON output.
The AI extracts modules, requirements, integrations, constraints, assumptions,
and unknowns. Each field has a confidence score (0.0–1.0). The user can request
plain-English corrections before approving.

### Stage 2 — Clarification Loop
Using the gaps and unknowns from Stage 1, the AI generates a minimum of 5
targeted questions — each citing a specific part of the transcript as the reason.
Users can answer, skip with a reason, or ask their own questions. The AI checks
each answer for completeness and generates follow-ups when needed.

### Stage 3 — Scope of Work
Combines Stage 1 extraction + Stage 2 Q&A into a full markdown SoW covering:
Executive Summary, In-Scope, Out-of-Scope, Modules & Deliverables, Integrations,
Constraints, Open Items, and Timeline. Requires at least one feedback revision
before the approval button activates.

### Stage 4 — Sprint Planning
The approved SoW is sent to Gemini which generates action-oriented tasks with
Fibonacci story points (1,2,3,5,8,13), acceptance criteria, and dependencies.
Tasks are organized into named 2-week sprints with a max 40 point limit.
Users can move tasks between sprints before approving.

### Stage 5 — Jira Sync
Three-step push: Epics → Issues → Sprints. Each step shows a preview and
requires explicit confirmation. The Jira REST API v3 creates Epics using
`customfield_10011`, links issues to Epics via `customfield_10014`, and
creates sprints via the Agile API. Story points use `customfield_10016`.

---

## 🏗️ Design Decisions

**Why FastAPI + Streamlit instead of a single framework?**
Separating the backend (FastAPI) from the frontend (Streamlit) means the AI
pipeline can be called from any client — browser, mobile app, or another
service. It also makes the code easier to test and reason about.

**Why SQLite instead of PostgreSQL?**
SQLite requires zero configuration and runs as a single file. For a tool used
by one team or a demo, it's more than sufficient. Swapping to PostgreSQL later
only requires changing the connection string in `database.py`.

**Why not use LangGraph state machine?**
The stage-gate logic is implemented directly in FastAPI + SQLite (each stage
has an `approved` boolean and a `StageStatus` enum). This is simpler to
understand and debug than a LangGraph graph. A LangGraph refactor would be
a natural next step for production.

**Why Gemini instead of OpenAI?**
Free tier availability and generous token limits make Gemini ideal for
development and demos. The LLM is fully swappable — change `get_llm()` in
`backend/services/llm.py` to use any LangChain-supported model.

**Why require a feedback round before SoW approval?**
The assessment specification requires human review at every stage. Forcing at
least one revision ensures the user has actually read the SoW rather than
rubber-stamping the first draft.

---

## ⚠️ Known Limitations

| Limitation | Detail |
|-----------|--------|
| Free tier rate limits | Gemini free tier has per-minute and per-day limits. The app retries automatically but very long transcripts may hit limits |
| Jira classic only | Team-managed (next-gen) Jira projects are not supported — Sprint API and Epic custom fields require classic projects |
| Sprint name length | Jira enforces a 30-character limit on sprint names. Names are auto-truncated |
| Single user | No authentication system — designed for single-user local use |
| No real-time streaming | AI responses are shown after completion, not streamed token by token |
| SQLite concurrency | SQLite does not support multiple simultaneous writers — not suitable for multi-user deployment without switching to PostgreSQL |
| Story points field | Uses `customfield_10016` for story points — may differ on some Jira instances |

---

## 🔄 Switching to a Different LLM

Open `backend/services/llm.py` and replace `get_llm()`:

**OpenAI:**
```python
from langchain_openai import ChatOpenAI
def get_llm():
    return ChatOpenAI(model="gpt-4o", temperature=0.2)
```

**Anthropic Claude:**
```python
from langchain_anthropic import ChatAnthropic
def get_llm():
    return ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0.2)
```

Add the corresponding API key to `.env` and install the package:
```bash
pip install langchain-openai   # for OpenAI
pip install langchain-anthropic # for Claude
```

---

## 📝 Adding a New Transcript

1. Create a new project in the sidebar
2. Paste or upload the transcript in Stage 1
3. Each project maintains completely independent state
4. No data from one project bleeds into another

---

## 🚀 Future Improvements

- [ ] Stream AI responses token by token using `st.write_stream()`
- [ ] Export SoW as PDF using `weasyprint`
- [ ] Add user authentication with `streamlit-authenticator`
- [ ] Refactor pipeline into a proper LangGraph `StateGraph`
- [ ] Add PostgreSQL support for multi-user deployment
- [ ] Add support for audio file transcription via Whisper API
- [ ] CI/CD pipeline with GitHub Actions

---

## 👤 Author

Built as a technical assessment for an AI Engineer role.