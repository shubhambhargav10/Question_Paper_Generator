"""
extractor.py – Extracts questions from uploaded files.

Strategy:
  .docx → Smart structural parser first (detects sections, questions, marks
           without any API call). Falls back to Gemini if structure is unclear.
  .pdf  → Convert pages to images → Gemini Vision
  images → Gemini Vision
  .txt  → Gemini text extraction
"""

import os
import io
import re
import json
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ─── Gemini prompt ────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """You are an expert at extracting exam questions from documents.

Analyze the provided content and extract ALL questions you can find.

For each question, return a JSON object with:
- "text": the full question text including any sub-points, options (a/b/c/d), or Assertion-Reason pairs
- "type": one of: "MCQ", "assertion_reason", "very_short", "short", "long", "case_based"
- "marks": marks if visible in the document (null if not found)
- "section": section label if visible (e.g., "A", "B", "C") — null if not found

Return ONLY a valid JSON array. No extra text, no markdown code fences.

Example output:
[
  {
    "text": "Law of Diminishing Marginal Utility states that:\\na) utility increases\\nb) utility decreases\\nc) utility remains same\\nd) none of these",
    "type": "MCQ",
    "marks": 1,
    "section": "A"
  },
  {
    "text": "Define economics.",
    "type": "very_short",
    "marks": 2,
    "section": "B"
  }
]
"""

# ─── Gemini helpers ───────────────────────────────────────────────────────────

def _init_gemini():
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY not set. Please add it to your .env file or Vercel environment."
        )
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    return genai

# Active model pool with automatic failover across fresh quota pools
ACTIVE_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash"
]

def _call_gemini_with_fallback(prompt, parts=None, gen_config=None):
    """Try models in sequence. If one hits daily quota (429), automatically fail over to the next!"""
    _init_gemini()
    import google.generativeai as genai
    last_err = None
    for model_name in ACTIVE_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            if parts:
                p_list = parts if isinstance(parts, list) else [parts]
                content = ([prompt] if isinstance(prompt, str) else list(prompt)) + p_list
            else:
                content = prompt
            return model.generate_content(content, generation_config=gen_config)
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "quota" in err_msg.lower():
                print(f"Model {model_name} quota exceeded, failing over to next model...")
                last_err = e
                continue
            else:
                raise e
    raise last_err or Exception("All available Gemini models have exceeded quota.")


def _parse_json_response(text: str) -> list:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return []
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return []


def extract_from_text(text: str) -> list:
    """Extract questions from raw text using Gemini."""
    prompt = EXTRACTION_PROMPT + f"\n\nContent to extract from:\n\n{text}"
    response = _call_gemini_with_fallback(prompt)
    return _parse_json_response(response.text)


def extract_from_image_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> list:
    """Extract questions from an image using Gemini Vision."""
    image_part = {"mime_type": mime_type, "data": image_bytes}
    response = _call_gemini_with_fallback([EXTRACTION_PROMPT, image_part])
    return _parse_json_response(response.text)


def extract_from_pdf_bytes(pdf_bytes: bytes) -> list:
    """Extract questions from PDF by converting pages to images → Gemini Vision."""
    try:
        import fitz
    except ImportError:
        raise ImportError("PyMuPDF not installed. Run: pip install pymupdf")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_questions = []
    seen_texts = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("jpeg")
        questions = extract_from_image_bytes(img_bytes, "image/jpeg")
        for q in questions:
            t = q.get("text", "").strip()
            if t and t not in seen_texts:
                seen_texts.add(t)
                all_questions.append(q)

    return all_questions


# ─── Smart docx structural parser ────────────────────────────────────────────
#
# Handles documents like:
#   SECTION A: MULTIPLE CHOICE QUESTIONS (1 Mark Each)
#   Q1. Question text
#   (a) Option A    (b) Option B
#   Q2. ...
#   SECTION B: SHORT ANSWER QUESTIONS (3 Marks Each)
#   Q21. ...
#
# Also handles the Podar 3-column table format (our own output format).

# Patterns for section headers
_SEC_HEADER_RE = re.compile(
    r"section\s*[-–:]?\s*([A-Z])\b.*?(?:\(([0-9]+)\s*marks?\s*each\))?",
    re.IGNORECASE,
)
# Patterns for question numbers: Q1., Q1:, 1., 1), (1)
_Q_NUM_RE = re.compile(
    r"^(?:Q\.?\s*)?(\d+)[.):]\s+(.+)",
    re.IGNORECASE | re.DOTALL,
)
# Marks in header or inline: (1 Mark Each), [3], (4 marks)
_MARKS_RE = re.compile(r"\((\d+)\s*marks?\s*(?:each)?\)", re.IGNORECASE)
_MARKS_BRACKET_RE = re.compile(r"\[(\d+)\]")

def _infer_type(marks: int | None, section_name: str, text: str = "") -> str:
    lower_text = text.lower()
    if "assertion" in lower_text and "reason" in lower_text:
        return "MCQ"
    if marks == 1: return "MCQ"
    if marks == 2: return "very_short"
    if marks == 3: return "short"
    if marks == 4:
        if "case" in lower_text or "source" in lower_text or "read the passage" in lower_text:
            return "case_based"
        return "short"
    if marks and marks >= 5: return "long"
    # fallback by section label
    sl = (section_name or "").upper()
    if sl == "A": return "MCQ"
    if sl == "B": return "very_short"
    if sl == "C": return "short"
    if sl == "D": return "case_based"
    if sl == "E": return "long"
    return "short"


def _is_section_header(text: str) -> tuple[bool, str | None, int | None]:
    """Returns (is_header, section_label, marks_per_q)."""
    if not text:
        return False, None, None
    line = text.strip()
    
    # Reject instruction sentences like "Section A contains 20 questions..." or "divided into four sections"
    if re.search(r"\b(contains?|divided|consists?|comprises?|questions?\s+of)\b", line, re.IGNORECASE):
        return False, None, None
        
    m = re.match(r"^(?:PART|SECTION)\s*[-–:]?\s*([A-Z])\b(?:\s*[-–:]\s*(.+))?", line, re.IGNORECASE)
    if m:
        label = m.group(1).upper()
        marks = None
        # 1. Multiplication pattern: (20 × 1 = 20 Marks), (6 * 3 = 18 Marks), (3 x 4 = 12 Marks)
        mm_mult = re.search(r"\d+\s*[×x*]\s*(\d+)\s*=\s*\d+\s*marks?", line, re.IGNORECASE)
        if mm_mult:
            marks = int(mm_mult.group(1))
        else:
            # 2. "(1 Mark Each)" or "(3 Marks Each)"
            mm_each = re.search(r"\(?(\d+)\s*marks?\s*each\)?", line, re.IGNORECASE)
            if mm_each:
                marks = int(mm_each.group(1))
            else:
                # 3. Explicit marks like "(1 Mark)", but not matching total marks preceded by "="
                mm = re.search(r"(?<!=)\s*\(?(\d+)\s*marks?\)?", line, re.IGNORECASE)
                if mm and int(mm.group(1)) <= 10:
                    marks = int(mm.group(1))
        
        # Default for Section A / MCQ
        if not marks and (re.search(r"multiple choice|mcq", line, re.IGNORECASE) or label == "A"):
            marks = 1
            
        return True, label, marks
    return False, None, None

def _extract_marks_from_text(text: str) -> int | None:
    """Pull explicit marks from question text, e.g. '(3 Marks)' or '[4]'."""
    m = _MARKS_RE.search(text)
    if m:
        return int(m.group(1))
    m = _MARKS_BRACKET_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _parse_docx_paragraphs(paragraphs: list) -> list:
    """
    Parse a list of paragraph texts into structured questions.
    Keeps all options and sub-parts together with their question.
    Ignores preambles and marks notes before question 1 starts.
    Attaches shared direction options (e.g. Assertion-Reason options) to relevant questions.
    """
    questions = []
    current_section = None
    current_marks_per_q = None
    current_q_lines = []
    current_q_marks = None
    current_q_num = 0
    active_directions = None

    def flush_question():
        nonlocal current_q_lines, current_q_marks
        if not current_q_lines:
            return
        text = "\n".join(current_q_lines).strip()
        text = re.sub(r"\*{3,}.*end of question paper.*", "", text, flags=re.IGNORECASE).strip()
        if not text:
            return
        if active_directions:
            start_q, end_q, opts = active_directions
            if start_q <= current_q_num <= end_q and opts:
                if not re.search(r"^\s*\([a-d]\)\s+[A-Za-z0-9]", text, re.MULTILINE):
                    text = text + "\n" + "\n".join(opts)
        marks = current_q_marks or current_marks_per_q
        questions.append({
            "text":    text,
            "type":    _infer_type(marks, current_section, text),
            "marks":   marks,
            "section": current_section,
        })
        current_q_lines = []
        current_q_marks = None

    for raw in paragraphs:
        line = raw.strip()
        if not line:
            continue

        if re.search(r"^\*{3,}.*end of question paper.*", line, re.IGNORECASE):
            flush_question()
            continue

        # Check if it's a section header
        is_hdr, sec_label, sec_marks = _is_section_header(line)
        if is_hdr:
            flush_question()
            current_section = sec_label
            current_marks_per_q = sec_marks
            current_q_num = 0  # Reset for new section
            active_directions = None
            continue

        # Shared Directions block (e.g. Directions for Questions 15 to 20)
        m_dir = re.search(r"directions?\s+for\s+questions?\s+(\d+)\s+to\s+(\d+)", line, re.IGNORECASE)
        if m_dir:
            flush_question()
            start_q, end_q = int(m_dir.group(1)), int(m_dir.group(2))
            opts = [l.strip() for l in line.split("\n") if re.match(r"^\([a-d]\)", l.strip(), re.IGNORECASE)]
            active_directions = (start_q, end_q, opts)
            continue

        # Check question number pattern with re.DOTALL so multiline options are kept!
        m = re.match(r"^(?:Q\.?|Question)?\s*(\d+)[\.:\)]\s*(.*)", line, re.IGNORECASE | re.DOTALL)
        if m:
            num = int(m.group(1))
            is_explicit = bool(re.match(r"^(?:Q\.?|Question)\s*\d+", line, re.IGNORECASE))
            if is_explicit or (num > current_q_num and num <= 60):
                flush_question()
                current_q_num = num
                q_text = m.group(2).strip()
                current_q_marks = _extract_marks_from_text(q_text)
                q_text_clean = _MARKS_RE.sub("", q_text).strip()
                current_q_lines = [q_text_clean] if q_text_clean else []
                continue

        # If we have not started a question yet in this section (e.g. preamble like "(20 × 1 = 20 Marks)"):
        if current_q_num == 0:
            # Check if this line specifies marks per question
            mm = re.search(r"\d+\s*[×x*]\s*(\d+)\s*=\s*\d+\s*marks?", line, re.IGNORECASE)
            if mm:
                current_marks_per_q = int(mm.group(1))
            elif re.search(r"\((\d+)\s*marks?\s*(?:each)?\)", line, re.IGNORECASE):
                current_marks_per_q = int(re.search(r"\((\d+)\s*marks?\s*(?:each)?\)", line, re.IGNORECASE).group(1))
            continue

        # Sub-part (e.g. 1., 2., 3. under Question 23, or options a/b/c/d) or continuation
        if current_q_lines is not None:
            current_q_lines.append(line)

    flush_question()
    return questions


def _is_question_table(table) -> bool:
    """
    Check if table is an actual question paper table (3 columns with Q#, Question, Marks)
    rather than an embedded statistical/data table or instructions box.
    """
    if len(table.columns) < 3:
        return False
    valid_q_rows = 0
    has_sec_header = False
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        if len(cells) < 3:
            continue
        c0, c1, c2 = cells[0], cells[1], cells[2]
        if not c0 and not c2 and re.search(r"section\s+[A-Z]", c1, re.IGNORECASE):
            has_sec_header = True
        elif re.match(r"^(?:Q\.?)?\s*\d+$", c0, re.IGNORECASE) and len(c1) >= 15:
            valid_q_rows += 1
    return has_sec_header or valid_q_rows >= 3


def _parse_docx_table(table) -> list:
    """
    Parse Podar-style 3-column table: [Q#, question text, [marks]]
    Section header rows have blank Q# and marks columns.
    """
    questions = []
    current_section = None
    current_marks_per_q = None

    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        if len(cells) < 3:
            continue

        q_num_cell, q_text_cell, marks_cell = cells[0], cells[1], cells[2]

        # Section header row: first and last cells are blank
        if not q_num_cell and not marks_cell:
            lines = [l.strip() for l in q_text_cell.splitlines() if l.strip()]
            if lines:
                sec_m = re.search(r"section\s+([A-Z])", lines[0], re.IGNORECASE)
                if sec_m:
                    current_section = sec_m.group(1).upper()
                for l in lines:
                    mm = _MARKS_RE.search(l)
                    if mm:
                        current_marks_per_q = int(mm.group(1))
                        break
            continue

        # Question row
        if q_text_cell:
            marks = None
            m = _MARKS_BRACKET_RE.search(marks_cell)
            if m:
                marks = int(m.group(1))
            elif marks_cell.isdigit():
                marks = int(marks_cell)
            marks = marks or current_marks_per_q

            questions.append({
                "text":    q_text_cell.strip(),
                "type":    _infer_type(marks, current_section, q_text_cell),
                "marks":   marks,
                "section": current_section,
            })

    return questions


def extract_from_docx_bytes(docx_bytes: bytes) -> list:
    """
    Smart docx extraction:
    1. Parse document elements in natural flow order (paragraphs and embedded data tables)
    2. Try table-based parsing only if the document contains a genuine question table
    3. Fall back to Gemini if structural parsing yields < 3 questions
    """
    import docx
    from docx import Document

    doc = Document(io.BytesIO(docx_bytes))

    # 1. First check if entire document is structured purely in question tables
    # (only if document has minimal paragraphs, e.g. < 10)
    q_tables = [t for t in doc.tables if _is_question_table(t)]
    if q_tables and len(doc.paragraphs) < 10:
        table_questions = []
        for table in q_tables:
            table_questions.extend(_parse_docx_table(table))
        if len(table_questions) >= 3:
            return table_questions

    # 2. Extract elements in document flow order (paragraphs + embedded data tables)
    flow_lines = []
    for child in doc.element.body:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = docx.text.paragraph.Paragraph(child, doc)
            t = p.text.strip()
            if t:
                flow_lines.append(t)
        elif tag == "tbl":
            tbl = docx.table.Table(child, doc)
            tbl_text = " ".join(c.text for row in tbl.rows for c in row.cells)
            # Skip general instructions box
            if re.search(r"\b(general\s+instructions?|time\s+allowed|maximum\s+marks)\b", tbl_text, re.IGNORECASE):
                continue
            if _is_question_table(tbl):
                continue
            # Embed data table rows (e.g. statistics tables) into question flow
            row_lines = []
            for row in tbl.rows:
                row_vals = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(row_vals):
                    row_lines.append("\t".join(row_vals))
            if row_lines:
                flow_lines.append("\n".join(row_lines))

    para_questions = _parse_docx_paragraphs(flow_lines)
    real_questions = [q for q in para_questions if q.get("section") is not None]

    if len(real_questions) >= 3:
        return real_questions

    if len(para_questions) >= 3:
        return para_questions

    if q_tables:
        table_questions = []
        for table in q_tables:
            table_questions.extend(_parse_docx_table(table))
        if len(table_questions) >= 3:
            return table_questions

    # 3. Fallback: send full text to Gemini
    all_text_parts = [l for l in flow_lines if l.strip()]
    full_text = "\n".join(all_text_parts)
    return extract_from_text(full_text)


# ─── Main dispatch ────────────────────────────────────────────────────────────

def extract_questions(file_bytes: bytes, filename: str, mime_type: str = None) -> list:
    """
    Main entry point. Dispatches to correct extractor based on file type.
    Returns list of question dicts: {text, type, marks, section}
    """
    fname = filename.lower()

    if fname.endswith(".pdf"):
        return extract_from_pdf_bytes(file_bytes)

    elif fname.endswith((".docx", ".doc")):
        return extract_from_docx_bytes(file_bytes)

    elif fname.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff")):
        ext_to_mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif",
            ".bmp": "image/bmp", ".tiff": "image/tiff",
        }
        ext = os.path.splitext(fname)[1]
        mt = ext_to_mime.get(ext, mime_type or "image/jpeg")
        return extract_from_image_bytes(file_bytes, mt)

    elif fname.endswith(".txt"):
        return extract_from_text(file_bytes.decode("utf-8", errors="ignore"))

    else:
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            return extract_from_text(text)
        except Exception:
            return []


# ─── Answer Key Generation ───────────────────────────────────────────────────

def generate_solutions(config: dict) -> dict:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    
    # We will build a prompt that includes all questions and asks for the answers
    sections_str = json.dumps(config.get("sections", []), indent=2)
    
    prompt = f"""You are an expert CBSE teacher generating a complete, accurate Answer Key.
I am providing you with the structure of a question paper in JSON format.
Each section has an array of "questions", and each question has a "text".

For EVERY question, generate the accurate, complete answer/solution in the "answer_text" field:
1. For 1-mark Multiple Choice Questions (MCQs): State the correct option letter and text clearly (e.g., "b) Realisation Account").
2. For Long Answer, Short Answer, or Case-Based Questions:
   - Many of these questions contain sub-parts labeled (1), (2), (3), (4) or (a), (b), (c), (d) or (i), (ii), (iii).
   - DO NOT treat these sub-parts as multiple-choice options!
   - You MUST solve and provide answers to ALL sub-parts thoroughly with full calculations, explanations, journal entries, or points.

Return the exact same JSON structure of `sections`, but modify each question object by adding an "answer_text" field containing your complete solution.

Input Sections:
{sections_str}

Respond ONLY with valid JSON.
"""
    
    try:
        response = _call_gemini_with_fallback(
            prompt,
            gen_config=genai.types.GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        resp_text = response.text
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].split("```")[0].strip()
            
        solved_sections = json.loads(resp_text)
        
        # Merge back into config
        config["sections"] = solved_sections
        return config
    except Exception as e:
        print(f"Error generating solutions: {e}")
        # We must raise the error so the frontend can display it to the user.
        # Otherwise, the user will download a blank answer key.
        raise Exception(f"Failed to generate answers: {str(e)}")


# ─── Blueprint Generation ───────────────────────────────────────────────────

def extract_blueprint_mapping(config: dict, portion_text: str) -> dict:
    import json
    import re
    
    # 1. First, parse chapters from portion_text deterministically
    raw_lines = [l.strip() for l in portion_text.strip().split("\n") if l.strip()]
    extracted_chapters = []
    for line in raw_lines:
        # Match lines like "Chapter 1: ...", "1. ...", "Unit 1: ...", or descriptive lines
        if re.search(r"^(chapter|unit|ch\.?|part|topic|\d+[\.:\-])", line, re.IGNORECASE):
            extracted_chapters.append(line)
        elif len(line) > 3 and not re.search(r"^(grade|class|subject|portion|syllabus|total|marks|time|date)", line, re.IGNORECASE):
            extracted_chapters.append(line)
            
    if not extracted_chapters:
        extracted_chapters = raw_lines[:12]  # Fallback to lines

    # Try Gemini with automatic model fallback
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            
            sections_str = json.dumps(config.get("sections", []), indent=2)
            
            prompt = f"""You are an expert teacher. 
I have a question paper structure and a syllabus/portion.
Your goal is to map the marks distribution across the syllabus chapters for a Blueprint.

Syllabus/Portion:
{portion_text}

Question Paper Sections:
{sections_str}

Please generate a JSON array of chapters. For each chapter, assign how many questions of each section type it gets, such that the TOTAL number of questions and marks across all chapters matches the paper configuration.
Return JSON format:
{{
  "chapters": [
    {{
      "chapter_name": "Name of chapter",
      "distribution": {{
        "Section A (Multiple Choice Questions)": {{"count": 2, "marks_per_q": 1, "total_marks": 2}},
        "Section B (Very Short Answer Type Questions)": {{"count": 1, "marks_per_q": 2, "total_marks": 2}}
      }},
      "total_chapter_marks": 4
    }}
  ]
}}

Make sure every chapter from the syllabus is included. Respond ONLY with valid JSON.
"""
            response = _call_gemini_with_fallback(
                prompt,
                gen_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    response_mime_type="application/json"
                )
            )
            resp_text = response.text
            if "```json" in resp_text:
                resp_text = resp_text.split("```json")[1].split("```")[0].strip()
            elif "```" in resp_text:
                resp_text = resp_text.split("```")[1].split("```")[0].strip()
                
            data = json.loads(resp_text)
            if data and data.get("chapters") and len(data["chapters"]) > 0:
                return data
        except Exception as e:
            print(f"Gemini blueprint generation failed ({e}), falling back to deterministic distribution...")

    # Fallback: Deterministic distribution across extracted chapters
    sections = config.get("sections", [])
    num_ch = max(1, len(extracted_chapters))
    
    # Initialize chapters
    chapters_data = []
    for ch_name in extracted_chapters:
        chapters_data.append({
            "chapter_name": ch_name,
            "distribution": {},
            "total_chapter_marks": 0
        })

    # Distribute questions of each section evenly across chapters
    for s_idx, sec in enumerate(sections):
        s_name = sec.get("name", chr(65 + s_idx))
        s_type = sec.get("type", "Questions")
        s_marks = sec.get("marks", 1)
        s_count = int(sec.get("count", 1))
        key = f"Section {s_name} ({s_type})"
        
        # Round-robin distribute questions
        for q_i in range(s_count):
            ch_idx = (s_idx * 3 + q_i) % num_ch
            ch_dist = chapters_data[ch_idx]["distribution"]
            if key not in ch_dist:
                ch_dist[key] = {"count": 0, "marks_per_q": s_marks, "total_marks": 0}
            ch_dist[key]["count"] += 1
            ch_dist[key]["total_marks"] += s_marks
            chapters_data[ch_idx]["total_chapter_marks"] += s_marks

    return {"chapters": chapters_data}
