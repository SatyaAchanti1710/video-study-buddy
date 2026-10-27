# 🎬 Video Study Buddy

A personal web app that turns a YouTube video, a PDF, a web page, or any pasted
transcript into study materials:

- **Notes** — a short summary, headings that follow the video's structure, bullet
  points with bolded key terms, and 3–5 key takeaways.
- **Flashcards** — 15–25 clickable flip cards (usually 20) mixing definitions,
  why/how questions, and application questions, with a shuffle button.
- **Practice test** — 10–15 questions (multiple choice, short answer, and 1–2
  critical-thinking questions). Answer in the app, submit, and see your score
  plus an answer key with explanations. Multiple choice is graded automatically.

You can download the notes as Markdown and the flashcards as an Anki-ready CSV.
Every pack is saved on your computer, so you can reopen it without paying to
generate it again.

Everything runs locally with Streamlit. The only thing that leaves your computer
is the source text you send to your chosen AI provider. If you want a public URL,
see [Publish it online](#publish-it-online-streamlit-community-cloud).

---

## What you need

1. **This project folder.**
2. **Python 3.11–3.14.** (3.12, 3.13, and 3.14 are fine; 3.15 is too new for one dependency.)
3. **An API key** from an AI provider (OpenAI, Anthropic, OpenRouter, Groq, or a
   local Ollama install).
4. **Internet access** for YouTube, web links, and the AI provider.
5. About 10 minutes the first time.

> **Using Freebuff Desktop?** Open the terminal panel at the project root — it is
> already in the right folder. Otherwise, open Terminal (macOS) or PowerShell
> (Windows) and `cd` into the folder that contains `app.py`.

> **A note for this Mac:** the built-in `/usr/bin/python3` is version 3.9, which
> is too old for current Streamlit. Homebrew Python 3.14 is installed, so use
> `python3.14` instead of `python3` in the commands below. On any computer,
> install Python 3.11+ from [python.org](https://www.python.org/downloads/) if
> `python3 --version` shows an older version.

---

## Quick start (3 commands)

If Python 3.11+ is already available and you want the short version:

```bash
# macOS / Linux (use python3.14 on this Mac)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.address 127.0.0.1
```

```powershell
# Windows PowerShell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py --server.address 127.0.0.1
```

Then complete **Step 4** (add your API key) and reload the page. If you get stuck,
use the detailed steps below.

> **This folder already has a `.venv` with everything installed.** In that case
> you can skip to Step 4, then run
> `.venv/bin/streamlit run app.py --server.address 127.0.0.1` (macOS/Linux) or
> `.venv\Scripts\streamlit run app.py --server.address 127.0.0.1` (Windows).

---

## Step-by-step setup

### Step 1 — Open a terminal in this folder

A **terminal** is a text window where you type commands instead of clicking
buttons. Open it, then move into the project folder:

```bash
cd path/to/this/folder
```

On macOS, you can type `cd ` (with a space), then drag the folder from Finder
into the terminal window and press Enter. On Windows, you can do the same from
File Explorer into PowerShell.

Check that you are in the right place:

```bash
ls        # macOS / Linux
dir       # Windows
```

You should see `app.py`, `requirements.txt`, and `study_buddy`.

### Step 2 — Check your Python version

```bash
python3 --version      # macOS / Linux
py --version           # Windows
```

You need **Python 3.11–3.14**. If it says 3.9 or 3.10:

- **macOS:** try `python3.14 --version`, `python3.13 --version`, or
  `python3.12 --version`. If one works, use that command name in the next step.
- **Windows:** install Python from python.org and tick **“Add Python to PATH”**
  during installation. Then reopen the terminal.

> **What is Python?** The programming language this app is written in. The
> `python` command starts it. The version matters because newer Python includes
> features the app's libraries rely on.

### Step 3 — Create a virtual environment and install the app's libraries

A **virtual environment** is a private toolbox for this project. It keeps the
app's libraries separate from the rest of your computer, so installing something
here can't break another project.

Create it (only once):

```bash
python3.14 -m venv .venv       # use your Python 3.11+ command here
```

Activate it (every time you open a new terminal):

```bash
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\Activate.ps1     # Windows PowerShell
```

Your prompt should now start with `(.venv)`. If PowerShell refuses to run the
script, run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Now install the dependencies:

```bash
python -m pip install -r requirements.txt
```

> **What is `pip`?** Python's installer. **Dependencies** are ready-made code
> packages the app uses. `requirements.txt` is the shopping list. The command can
> take a minute or two and print a lot of text; that's normal. Warnings about pip
> being out of date are safe to ignore. You should end with a line like
> `Successfully installed ...`.

### Step 4 — Add your API key

The app reads settings from a file named **`.env`** in this folder. A `.env` file
is already here with a placeholder key; `.env.example` is the same file for
reference. If `.env` ever goes missing, duplicate `.env.example` and rename the
copy to `.env` (`cp .env.example .env` on macOS/Linux, `copy .env.example .env`
on Windows).

Open `.env` in any plain-text editor:

- **macOS:** `open -e .env`
- **Windows:** `notepad .env`
- Or open it in VS Code / any editor. It must stay named `.env`, not `.env.txt`.

Find this line:

```dotenv
LLM_API_KEY=sk-paste-your-key-here
```

Replace the placeholder with your real key, with **no quotes and no spaces**:

```dotenv
LLM_API_KEY=sk-proj-abc123yourrealkey
```

Save the file. Then reload the app in your browser (or restart the terminal
command if it isn't running yet).

> **What is an API key?** A long password that lets the app use your AI account
> and bill you for usage. Treat it like a credit card number: never post it,
> email it, or commit it to a git repository. This project's `.gitignore` already
> excludes `.env`.

#### Where to get a key

**OpenAI (the default setup)**

1. Go to <https://platform.openai.com/api-keys> and sign in.
2. Choose **Create new secret key**, name it “Video Study Buddy”, and copy the key
   that starts with `sk-`. You cannot see it again.
3. API usage is **pay-as-you-go and separate from a ChatGPT Plus subscription**.
   Add a small amount of credit under **Billing** and set a spending limit.
4. Keep the default model `gpt-4o-mini`; it is inexpensive and follows JSON
   instructions well.

**Anthropic (Claude)**

1. Go to <https://console.anthropic.com/> → **API Keys** → **Create Key**.
2. Put the key in `.env`, and change these lines:

```dotenv
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-your-key-here
LLM_MODEL=claude-sonnet-4-5
```

**OpenRouter / Groq / other OpenAI-compatible providers**

See [Choosing a different AI provider](#choosing-a-different-ai-provider) below.

### Step 5 — Run the app

With the environment active:

```bash
streamlit run app.py --server.address 127.0.0.1
```

You should see text like:

```
Local URL: http://localhost:8501
```

Streamlit usually opens your browser automatically. If not, open that address
yourself. Keep the terminal window open while you use the app. To stop the app,
press **Ctrl+C** in the terminal.

> **What is `localhost`?** Your own computer. `8501` is the port (a numbered
> door) the app is using. The `--server.address 127.0.0.1` part binds the app to
> this computer only, so other devices on your network cannot open it. (The repo's
> config deliberately leaves the address unset so the cloud deployment works.) If
> the port is busy, run `streamlit run app.py --server.address 127.0.0.1 --server.port 8502`
> and open the address it prints.

---

## Sections: General and Chemistry

At the top of the page you can pick a **section**:

- **🎬 General** — works for any video.
- **🧪 Chemistry** — the same app, but every AI request is additionally told this
  is a chemistry lesson. Notes, flashcards, and questions then focus on
  substance names and formulas, reaction equations, conditions (temperature,
  solvent, catalyst), observations, mechanism steps in order, and calculations
  with the units and quantities the video gives.
- **📄 Documents & web** — upload a PDF or paste a link to a PDF or article page.
  The page's menu, ads, and footer are stripped, and the notes follow the
  document's own headings. Numbers, names, and quotations are kept exactly as
  written. Scanned PDFs with no selectable text are refused, not guessed at, and
  pages that need a login or render their text with JavaScript are refused too.

Both sections use identical rules about grounding: material still comes only
from the transcript, and the chemistry prompts explicitly forbid balancing,
completing, or correcting an equation the video does not state. Nothing is added
from outside the video, so the chemistry section cannot supply a missing product
or constant.

Saved packs are kept separately: the sidebar library and the section switcher are
linked, so the Chemistry section lists only packs you made in Chemistry, and
the General section lists the rest. Each saved pack shows which section made it.

## Using the app

1. Pick a **section** at the top (General, Chemistry, or Documents & web).
2. In General or Chemistry, paste a **YouTube link** (for example `https://www.youtube.com/watch?v=…`) or
   paste the **full transcript text**. In Documents & web, upload a PDF or paste
   a link instead.
3. Optionally add a title. For links, the YouTube title is used automatically.
4. Choose **Easy / Medium / Hard** and the number of test questions in the
   left sidebar.
5. Click **Generate study materials** and wait. Long videos take longer.
6. Use the three tabs:
   - **Notes** — read, then download as Markdown if you want.
   - **Flashcards** — click a card to flip it, use Previous/Next, or press the
     arrow keys after clicking the card. Shuffle reorders the deck.
   - **Practice test** — answer every question, click **Submit answers**, and
     review the score and explanations. **Retake test** clears your answers.
7. Every pack is saved automatically. Find it in **Saved packs** in the sidebar
   to reopen it later, or delete it there.

### If the YouTube transcript can't be fetched

YouTube sometimes blocks transcript downloads, has captions turned off, or has
no captions at all. The app will say so and nothing will be generated.

Fix it in one minute:

1. Open the video on YouTube.
2. Expand the description (click **“…more”**).
3. Click **Show transcript**.
4. Select and copy the transcript text.
5. Paste it into the app's text box and click **Generate study materials** again.

The app refuses transcripts shorter than 150 words on purpose: with too little
text, any “study material” would be invented rather than derived from the video.

---

## Choosing a different AI provider

Open `.env`, change the values, save, and reload the app. No code changes are
needed. `LLM_PROVIDER=openai` means “any API that behaves like OpenAI's”, which
covers many providers. This project is currently configured for FreeLLMAPI on
this Mac; the blocks below are alternatives.

### FreeLLMAPI (local router — currently configured here)

[FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi) is an open-source,
OpenAI-compatible router that stacks free provider tiers behind one key. The
desktop app or server must be running on this computer whenever you generate.

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=freellmapi-your-unified-key
LLM_BASE_URL=http://127.0.0.1:31415/v1
LLM_MODEL=auto
LLM_JSON_MODE=true
```

- **Desktop app:** keep the menu-bar app running. Its API is on port `31415`
  (the dashboard is at <http://127.0.0.1:31415>).
- **Docker/server install:** the API is usually at
  `http://localhost:3001/v1` instead.
- `auto` lets the router choose; `auto:fast` and `auto:smart` bias the choice.
  A specific model id from the FreeLLMAPI dashboard also works.
- If the local router isn't running, the app will report that it cannot reach
  the provider. Start FreeLLMAPI, then reload the study app.

### OpenAI

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-key
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=
```

### Anthropic (Claude)

```dotenv
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-your-key
LLM_MODEL=claude-sonnet-4-5
LLM_BASE_URL=
```

### OpenRouter (one key, many models)

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=sk-or-v1-your-key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-4o-mini
```

Browse model names at <https://openrouter.ai/models>. Use one that supports
“structured outputs” or JSON mode for the most reliable results.

### Groq (fast, has a free tier)

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=gsk_your-key
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

Use a current model name from <https://console.groq.com/docs/models>.

### Ollama (free, runs on your computer, no API bill)

1. Install [Ollama](https://ollama.com/), then download a model:
   `ollama pull llama3.1`
2. Use:

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1
LLM_JSON_MODE=true
```

Local models are convenient but weaker at strict JSON and quality checks. If one
keeps failing, try a larger model or switch to a hosted provider. If Ollama
rejects the request, set `LLM_JSON_MODE=false`.

### Any other OpenAI-compatible endpoint

Set `LLM_BASE_URL` to its base URL (it should end in `/v1` for most providers),
`LLM_MODEL` to the exact model name, and `LLM_API_KEY` to its key.

> **After editing `.env`:** reload the browser page. The app re-reads `.env` on
> each interaction. If a value still looks stale, stop the app with Ctrl+C and
> run `streamlit run app.py --server.address 127.0.0.1` again.

---

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `command not found: streamlit` or `No module named streamlit` | The virtual environment isn't active, or dependencies aren't installed. Run `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\Activate.ps1` (Windows), then `python -m pip install -r requirements.txt`. You can also run `.venv/bin/streamlit run app.py` directly. |
| `Could not find a version that satisfies the requirement` | Your Python is too old. Check `python3 --version`; install Python 3.11+ and recreate `.venv`. |
| `No transcript could be fetched` / YouTube blocked | Wait a few minutes, try another video, or copy the transcript manually using **Show transcript**. |
| `This video has no captions` | Use **Show transcript** on YouTube and paste the text. |
| `The transcript is only N words long` | Paste the complete transcript. Only lower `MIN_TRANSCRIPT_WORDS` in `.env` if you accept weaker results. |
| `rejected the API key (HTTP 401/403)` | Re-copy the key into `.env` carefully. Remove quotes and spaces. Make sure you copied the whole key. |
| `could not find the model` (HTTP 404) | Check `LLM_MODEL` spelling and `LLM_BASE_URL` for your provider. |
| HTTP 429 | You're rate-limited or out of credits. Wait, or check your provider's billing page. |
| `The AI's answer was cut off` | Raise `LLM_MAX_OUTPUT_TOKENS` in `.env` (for example to `12000`) and try again. |
| `failed the app's quality checks` | The model returned invalid JSON or quotes that aren't in the transcript. Try again, use a stronger model, or shorter transcript. |
| The app hangs for a long time | Long sources make several API calls. Check the terminal for errors; increase `LLM_TIMEOUT` if your provider is slow. |
| `This PDF has no selectable text` | It is a scan or photos of pages. Run “Recognise text” (OCR) in a PDF reader, or use a text-based PDF. |
| `No readable article text was found` | The page needs a login, is mostly images or video, or builds its text with JavaScript. Try another link, or save the page as a PDF and upload it. |
| A web link will not open | The site may block automatic readers. Download the page as a PDF from your browser (Print → Save as PDF) and upload that instead. |
| `Address already in use` | Another app is on port 8501. Run `streamlit run app.py --server.port 8502`. |
| Browser shows an error page | Copy the **Local URL** from the terminal and open it manually. |
| Saved packs not appearing | Look in the `data/packs` folder. Check the terminal for a permission error. |
| `SSL: CERTIFICATE_VERIFY_FAILED` (macOS) | If you installed Python from python.org, run its “Install Certificates.command” once, or use Homebrew Python. |
| Strange/invented-sounding notes | Try a stronger model, a cleaner transcript, or generate again. The app blocks unsupported flashcards/questions, but notes are summarised text and can still be imperfect. |

For anything else, read the **Technical details** expander that appears under an
error in the app, and check the terminal window for the traceback.

---

## How it works (the short version)

1. A YouTube link is resolved with `youtube-transcript-api`; the transcript is
   saved with timestamps roughly every 45 seconds. A pasted transcript is used
   as-is.
2. Very short transcripts are rejected before any AI call.
3. Long transcripts are split into chunks (about 9,000 characters). Each chunk is
   sent to the AI separately to extract a **factual brief**: headings, bullets,
   key terms, and verbatim quotes. The chosen section adds its extra instructions
   to every one of these requests, not just the final three.
4. If the combined briefs are too large, they are merged in groups, then
   condensed. That's the map-reduce step that handles long videos.
5. Three final AI calls write the **notes**, the **flashcards**, and the
   **practice test** from the brief only. Flashcards and test questions are
   requested in parallel so the wait is shorter.
6. Every result is checked with Pydantic (the required JSON shape and counts).
   Every flashcard and question must include a `source_quote` that really occurs
   in the source text — otherwise it is rejected and the app asks the model to fix
   it once. The app never guesses.
7. The finished pack is saved as a JSON file in `data/packs/`.

The app caps transcripts at 30 chunks (`MAX_TRANSCRIPT_CHUNKS` in `.env`) to
avoid an accidentally huge bill. Videos longer than that get a clear message.

---

## Cost and privacy

- **AI calls:** one per transcript chunk, plus merging if needed, plus three
  final calls (and occasionally a repair call). A typical 20–60 minute talk is a
  few cents with `gpt-4o-mini`; premium models and very long videos cost more.
  FreeLLMAPI uses your free provider tiers, subject to their quotas and terms.
  Check your provider's current pricing and set a spending limit.
- **What leaves your computer:** the source text (transcript, PDF text, or
  article text) and prompts are sent to your configured AI provider under their
  privacy policy. YouTube receives the video lookup; a website you paste receives
  a normal page request. Uploaded PDFs are read locally. Nothing else is sent
  anywhere.
- **What stays local:** your API key (`.env`), preferences, and all saved study
  packs (`data/packs/*.json`). There is no account, analytics, or app server.
- **Don't paste confidential material** into a hosted AI provider. A local Ollama
  setup keeps everything on your computer, at some cost in quality.

---

## Files in this project

| File | What it does |
| --- | --- |
| [app.py](app.py) | The Streamlit interface: input, tabs, flashcard viewer, test grading, library, downloads. |
| [study_buddy/transcripts.py](study_buddy/transcripts.py) | YouTube URL parsing, caption fetching, language fallback, minimum-length check. |
| [study_buddy/pipeline.py](study_buddy/pipeline.py) | Chunking, map-reduce, question mix, automatic repair. |
| [study_buddy/subjects.py](study_buddy/subjects.py) | The General, Chemistry, and Documents & web sections: page wording plus the extra instructions added to each prompt. |
| [study_buddy/documents.py](study_buddy/documents.py) | Reads text from a PDF or an article page, with clear refusals for scans, logins, and empty pages. |
| [study_buddy/prompts.py](study_buddy/prompts.py) | All the AI instructions and JSON schemas. Start here if you want to tune the style. |
| [study_buddy/schema.py](study_buddy/schema.py) | Pydantic models and the “is this quote really in the transcript?” check. |
| [study_buddy/llm.py](study_buddy/llm.py) | OpenAI-compatible and Anthropic clients, retries, JSON extraction, friendly errors. |
| [study_buddy/config.py](study_buddy/config.py) | Reads `.env`, plus Streamlit Cloud secrets when deployed, and exposes settings. |
| [study_buddy/storage.py](study_buddy/storage.py) | Saves, lists, loads, and deletes packs in `data/packs/`. |
| [study_buddy/formatting.py](study_buddy/formatting.py) | Markdown and CSV exports, safe filenames, key-term bolding. |
| [study_buddy/cards.py](study_buddy/cards.py) | The HTML/CSS/JavaScript flip-card viewer. |
| [.env.example](.env.example) | Template with comments for every setting. |
| [.streamlit/config.toml](.streamlit/config.toml) | Upload limit and Streamlit usage stats. Local binding is done in the run command. |
| [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) | Template for the Secrets box on Streamlit Community Cloud. |
| [requirements.txt](requirements.txt) | Pinned versions of the Python libraries. |

Useful knobs in `.env`:

- `TRANSCRIPT_CHUNK_CHARS` — smaller chunks mean more calls but more detail.
- `LLM_MAX_WORKERS` — how many chunks are processed in parallel (lower it if you
  hit rate limits).
- `LLM_MAX_OUTPUT_TOKENS` — raise it if answers are cut off.
- `MIN_TRANSCRIPT_WORDS` — the safety floor (150 by default).
- `STUDY_DATA_DIR` — move saved packs somewhere else.

---

## Publish it online (Streamlit Community Cloud)

Streamlit Community Cloud hosts this kind of app for free. The catch is that it
runs on Streamlit's servers, not your Mac, so three things change:

- **Your local FreeLLMAPI router cannot be reached.** Use a cloud provider
  (OpenAI, Anthropic, OpenRouter, Groq) and put that key in Streamlit's Secrets.
- **Saved packs are temporary.** The server's disk is reset when the app sleeps,
  reboots, or redeploys. Download notes/CSV for anything you want to keep, or
  keep using the local copy for your library.
- **The URL is public.** Set `APP_PASSWORD`, or anyone who finds it can generate
  study packs on your API balance. The app shows a password screen whenever that
  setting is present.

### Steps

1. **Put the project on GitHub.** From this folder:

   ```bash
   git init
   git add .
   git commit -m "Video Study Buddy"
   gh repo create video-study-buddy --private --source=. --remote=origin --push
   ```

   `.env`, `.venv/`, `data/`, and `.streamlit/secrets.toml` are already ignored,
   so no key or personal pack is uploaded. Use `--public` instead of `--private`
   if you prefer.

2. Go to <https://share.streamlit.io> and sign in with GitHub.
3. Click **Create app** → **Deploy a public app from GitHub**, then choose the
   repository, branch `main`, and main file `app.py`.
4. Open **Advanced settings** → **Python version** and pick **3.12**.
5. In **Secrets**, paste this (replace the values):

   ```toml
   LLM_PROVIDER = "openai"
   LLM_API_KEY = "sk-your-cloud-provider-key"
   LLM_MODEL = "gpt-4o-mini"
   LLM_BASE_URL = "https://api.openai.com/v1"
   APP_PASSWORD = "choose-a-long-passphrase"
   ```

   The same template is in
   [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example). These
   values are read automatically on the cloud; your local `.env` still wins when
   you run the app yourself.
6. Click **Deploy**. The first build takes a few minutes.

### After it is live

- Open the URL, enter `APP_PASSWORD`, and generate one pack to confirm the key
  works. If you see “No API key found”, the Secrets box is missing or misspelled.
- To update the app, push to GitHub; Streamlit redeploys automatically.
- Free apps sleep after a period of inactivity. The first visit afterwards takes
  a few seconds to wake it.
- YouTube sometimes blocks transcript downloads from data-centre IPs. If that
  happens in the cloud but works locally, paste the transcript instead.
- Change `APP_PASSWORD` in Secrets if you ever share the link by mistake.

---

## Every day after setup

```bash
source .venv/bin/activate          # macOS/Linux
.venv\Scripts\Activate.ps1         # Windows
streamlit run app.py --server.address 127.0.0.1
```

Press **Ctrl+C** in the terminal when you're done. Saved packs are waiting in the
sidebar next time.

---

## Plain-English glossary

- **Terminal** — a text window where you type commands.
- **Command** — a line of text you type and run with Enter.
- **`cd`** — “change directory”, i.e. move into a folder.
- **Virtual environment (`venv`)** — a private folder of libraries for one
  project. Activate it before installing or running.
- **`pip`** — Python's package installer.
- **Dependency / package / library** — reusable code someone else wrote.
- **`.env`** — a plain-text file of settings and secrets. Keep it private.
- **Environment variable** — a named setting the app reads at startup.
- **API** — a way for one program to ask another program to do something.
- **API key** — the secret password for that access, tied to your billing.
- **LLM** — large language model, the AI that writes the notes and questions.
- **Token** — a word fragment AI providers count for pricing and limits. About
  4 characters of English is roughly one token.
- **JSON** — a structured text format made of `{ "keys": "values" }`. The AI
  returns JSON so the app can reliably display each part.
- **Markdown** — simple text formatting (`**bold**`, `# heading`) used by the
  notes download.
- **CSV** — a spreadsheet-style text file; Anki imports the flashcard CSV.
- **Anki** — a popular flashcard app.
- **YouTube transcript / captions** — the text of what is said in a video.
- **Traceback** — the technical error report Python prints. Useful when asking
  for help.
- **localhost / port** — your own computer and the numbered door the app listens
  on.

---

## A note on results

The app is deliberately strict: it will stop with an error rather than invent
content, and it rejects cards/questions whose quotes aren't in the transcript.
That means you may occasionally see “quality checks failed” after a long wait.
Generate again, switch to a model that follows JSON instructions well (such as
`gpt-4o-mini` or Claude), or paste a cleaner transcript.

Notes are summaries, not a substitute for the video. Always sanity-check anything
you plan to rely on.
