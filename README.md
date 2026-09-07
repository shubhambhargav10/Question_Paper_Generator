# Question Paper Generator

A web app that generates professionally formatted Word (.docx) question papers for Podar World School Vapi.

Upload questions from **any source** (photos, PDFs, Word files, screenshots) and the AI extracts them — then generates a perfectly formatted question paper matching the school's exact layout.

---

## Features

- 📸 **Accepts anything** — mobile photos, screenshots, PDFs, Word docs, plain text
- 🤖 **AI-powered extraction** via Google Gemini Vision
- 📄 **Exact school layout** — logo, header, instructions, 3-column question table
- 🎯 **Supports 30 / 50 / 80 marks** (or custom)
- 🔀 **Set B generation** — auto-shuffles questions within sections
- ⬇️ **Downloads as .docx** — ready to print

---

## Quick Start (Local)

```bash
# 1. Clone / open the project
cd question_paper_generator

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your Gemini API key
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key_here

# 4. Run the app
python api/index.py

# 5. Open in browser
open http://localhost:5000
```

---

## Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Set your API key in Vercel dashboard:
# Settings → Environment Variables → GEMINI_API_KEY
```

> **Note**: On Vercel's free (Hobby) plan, serverless functions time out at **10 seconds**. Large PDFs with many pages may be slow — consider upgrading to Pro (60s timeout) if needed.

---

## Project Structure

```
question_paper_generator/
├── api/
│   ├── index.py         # Flask app — all routes
│   ├── generator.py     # .docx generation (exact Podar layout)
│   └── extractor.py     # Gemini Vision question extraction
├── public/
│   ├── index.html       # 4-step wizard UI
│   ├── style.css        # Styling
│   └── app.js           # Frontend logic
├── assets/
│   └── logo.jpg         # Podar World School logo
├── vercel.json          # Vercel deployment config
├── requirements.txt
└── .env.example
```

---

## How It Works

### Step 1 — Paper Details
Enter class, subject, total marks (30/50/80/custom), duration, date.

### Step 2 — Sections
Auto-populated based on marks. Adjust question counts per section. Running total must match.

### Step 3 — Upload Questions
Drag-drop files or paste text. Click **Extract with AI** — Gemini reads your content and returns structured questions. Assign each to a section.

### Step 4 — Review & Generate
Preview all sections and their questions. Optionally check "Generate Set B" for a shuffled version. Click Generate to download your `.docx`.

---

## Section Breakdown Presets

| Marks | Sec A (MCQ×1) | Sec B (VSA×2) | Sec C (SA×3) | Sec D (Case×4) | Sec E (LA×5) |
|-------|---------------|---------------|--------------|----------------|--------------|
| 30    | 8             | 2             | 3            | 1              | 1            |
| 50    | 16            | 4             | 4            | 1              | 2            |
| 80    | 20            | 5             | 6            | 3              | 4            |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key (required for question extraction) |
| `PORT` | Port for local server (default: `5000`) |

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com).
