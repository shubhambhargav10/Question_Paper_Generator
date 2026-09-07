def _repeat_table_header(table):
    """Repeat the table header row on every new page."""
    header_tr = table.rows[0]._tr.get_or_add_trPr()
    header_tr.append(OxmlElement("w:tblHeader"))

import re
"""
generator.py – Generates Podar World School question paper .docx files
that exactly replicate the reference document format.
"""

import io
import os
from copy import deepcopy
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import random

# ─── Section presets ────────────────────────────────────────────────────────

SECTION_PRESETS = {
    30: [
        {"name": "A", "type": "Multiple Choice Questions",         "marks": 1, "count": 8,
         "note": "(Q1 to Q5 are standard MCQs, Q6 to Q8 are Assertion-Reason)"},
        {"name": "B", "type": "Very Short Answer Type Questions",  "marks": 2, "count": 2},
        {"name": "C", "type": "Short Answer Type Questions",       "marks": 3, "count": 3},
        {"name": "D", "type": "Case/Source-Based Questions",       "marks": 4, "count": 1},
        {"name": "E", "type": "Long Answer Type Questions",        "marks": 5, "count": 1},
    ],
    50: [
        {"name": "A", "type": "Multiple Choice Questions",         "marks": 1, "count": 16,
         "note": "(Q1 to Q10 are standard MCQs, Q11 to Q16 are Assertion-Reason)"},
        {"name": "B", "type": "Very Short Answer Type Questions",  "marks": 2, "count": 4},
        {"name": "C", "type": "Short Answer Type Questions",       "marks": 3, "count": 4},
        {"name": "D", "type": "Case/Source-Based Questions",       "marks": 4, "count": 1},
        {"name": "E", "type": "Long Answer Type Questions",        "marks": 5, "count": 2},
    ],
    80: [
        {"name": "A", "type": "Multiple Choice Questions",         "marks": 1, "count": 20,
         "note": "(Q1 to Q14 are standard MCQs, Q15 to Q20 are Assertion-Reason)"},
        {"name": "B", "type": "Very Short Answer Type Questions",  "marks": 2, "count": 5},
        {"name": "C", "type": "Short Answer Type Questions",       "marks": 3, "count": 6},
        {"name": "D", "type": "Case/Source-Based Questions",       "marks": 4, "count": 3},
        {"name": "E", "type": "Long Answer Type Questions",        "marks": 5, "count": 4},
    ],
}

# EMU conversions matching original documents
FONT_SIZE_HEADER = 152400   # 12pt
FONT_SIZE_INSTR  = 127000   # 10pt
FONT_SIZE_BODY   = 139700   # 11pt
FONT_SIZE_TABLE  = 139700   # 11pt

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.jpg")


def _set_cell_border(cell, **kwargs):
    """Set borders on a table cell."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = OxmlElement(f"w:{side}")
        val = kwargs.get(side, "none")
        tag.set(qn("w:val"), val)
        if val != "none":
            tag.set(qn("w:sz"), "4")
            tag.set(qn("w:space"), "0")
            tag.set(qn("w:color"), "000000")
        tcBorders.append(tag)
    tcPr.append(tcBorders)


def _set_table_border(table, val="single"):
    """Set uniform border on entire table."""
    tbl = table._tbl
    tblPr = tbl.tblPr
    tblBorders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = OxmlElement(f"w:{side}")
        tag.set(qn("w:val"), val)
        tag.set(qn("w:sz"), "4")
        tag.set(qn("w:space"), "0")
        tag.set(qn("w:color"), "000000")
        tblBorders.append(tag)
    tblPr.append(tblBorders)


def _bold_run(para, text, size_emu=FONT_SIZE_HEADER, italic=False):
    run = para.add_run(text)
    run.bold = True
    run.italic = italic
    run.font.size = Emu(size_emu)
    return run


def _italic_run(para, text, size_emu=FONT_SIZE_BODY):
    run = para.add_run(text)
    run.italic = True
    run.font.size = Emu(size_emu)
    return run


def _normal_run(para, text, size_emu=FONT_SIZE_BODY, italic=False):
    run = para.add_run(text)
    run.bold = False
    run.italic = italic
    run.font.size = Emu(size_emu)
    return run

def _extract_ans_letter(ans_text):
    if not ans_text:
        return None
    ans_clean = ans_text.strip().lower()
    m = re.search(r'(?:option|ans|answer|choice)?\s*\(?([a-d])\)?[.:\s]', ans_clean + ' ')
    if m:
        return m.group(1).lower()
    if ans_clean in ['a', 'b', 'c', 'd']:
        return ans_clean
    return None

def _render_mcq_line_in_docx(doc, line_text, correct_letter):
    p = doc.add_paragraph()
    pattern = r"(?:^\s*|(?:\t|\s{2,}))(?=\(?([a-d])\)?[.:\)])"
    matches = list(re.finditer(pattern, line_text, flags=re.IGNORECASE))
    
    if not matches:
        _normal_run(p, f"   {line_text}", FONT_SIZE_BODY)
        return

    opt_starts = [m.end() for m in matches]
    opt_starts.append(len(line_text))
    pieces = []
    for i in range(len(opt_starts) - 1):
        segment = line_text[opt_starts[i]:opt_starts[i+1]].strip()
        if segment:
            m_opt = re.search(r"^\(?([a-d])\)?[.:\)]", segment, flags=re.IGNORECASE)
            opt_letter = m_opt.group(1).lower() if m_opt else None
            is_correct = bool(opt_letter and correct_letter and opt_letter == correct_letter)
            pieces.append((segment, is_correct))
            
    for i, (seg, is_bold) in enumerate(pieces):
        if i == 0:
            _normal_run(p, "   ", FONT_SIZE_BODY)
        else:
            _normal_run(p, "    ", FONT_SIZE_BODY)
            
        if is_bold:
            _bold_run(p, seg, FONT_SIZE_BODY)
        else:
            _normal_run(p, seg, FONT_SIZE_BODY)

def _split_inline_options(q_lines):
    if len(q_lines) == 1:
        text = q_lines[0]
        parts = re.split(r"\s+(?=\([a-d]\)|[a-d]\))", text, flags=re.IGNORECASE)
        if len(parts) >= 3:
            return [p.strip() for p in parts if p.strip()]
    return q_lines


def _set_col_width(table, col_idx, width_cm):
    for row in table.rows:
        row.cells[col_idx].width = Cm(width_cm)


def _total_questions(sections):
    return sum(s["count"] for s in sections)


def _build_instruction_detail(sections, total_marks):
    lines = []
    q_num = 1
    for sec in sections:
        name         = sec["name"]
        count        = sec["count"]
        marks        = sec["marks"]
        note         = sec.get("note", "")
        attempt      = sec.get("attemptCount") or sec.get("attempt_count")
        q_end        = q_num + count - 1

        if marks == 1:
            base = f"  Section - {name} has {count} MCQs of {marks} mark each."
        else:
            base = f"  Section - {name} has {count} question{'s' if count > 1 else ''} of {marks} mark{'s' if marks > 1 else ''} each."

        if attempt and int(attempt) < count:
            base += f" (Attempt any {attempt})"
        if note:
            base += f" {note}"
        lines.append(base)
        q_num = q_end + 1
    return lines


def generate_question_paper(config: dict) -> bytes:
    """
    config keys:
      school_name   str  – e.g. "PODAR WORLD SCHOOL VAPI"
      grade         str  – e.g. "XI"
      subject       str  – e.g. "ECONOMICS"
      paper_set     str  – "A" or "B"
      total_marks   int  – 30 / 50 / 80 or custom
      duration      str  – e.g. "2 hrs 10 min"
      date          str  – e.g. ".07.2026"
      sections      list – list of section dicts (name, type, marks, count, questions)
                           if None, use SECTION_PRESETS
      generate_set_b bool – shuffle questions for Set B

    Returns bytes of the .docx file.
    """
    school_name  = config.get("school_name", "PODAR WORLD SCHOOL VAPI")
    grade        = config.get("grade", "XI")
    subject      = config.get("subject", "ECONOMICS")
    paper_set    = config.get("paper_set", "A").upper()
    total_marks  = int(config.get("total_marks", 50))
    duration     = config.get("duration", "2 hrs 10 min")
    date_str     = config.get("date", "")
    sections     = config.get("sections", None)
    generate_b   = config.get("generate_set_b", False)

    if sections is None:
        sections = SECTION_PRESETS.get(total_marks, SECTION_PRESETS[50])

    # If Set B requested, shuffle questions within each section
    if generate_b or paper_set == "B":
        paper_set = "B"
        sections = _shuffle_sections(sections)

    doc = Document()

    # ── Page setup ──────────────────────────────────────────────────────────
    section = doc.sections[0]
    section.page_height = Cm(27.94)
    section.page_width  = Cm(21.59)
    section.top_margin    = Cm(1.75)
    section.bottom_margin = Cm(1.91)
    section.left_margin   = Cm(2.54)
    section.right_margin  = Cm(2.54)

    style = doc.styles["Normal"]
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after  = Pt(0)

    usable_width_cm = 21.59 - 2.54 - 2.54  # 16.51 cm
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER

    # ── Header Box (1x1 Table) ───────────────────────────────────────────────
    header_table = doc.add_table(rows=1, cols=1)
    _set_table_border(header_table, "single")
    cell = header_table.cell(0, 0)
    cell.width = Cm(usable_width_cm)

    # 1. Logo
    logo_p = cell.add_paragraph()
    logo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if os.path.exists(LOGO_PATH):
        run = logo_p.add_run()
        run.add_picture(LOGO_PATH, height=Cm(1.8))
    else:
        run = logo_p.add_run("                                                           ")
        run.font.size = Emu(127000)

    # 2. School Name & Details
    def _add_center_bold(text):
        p = cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _bold_run(p, text, FONT_SIZE_HEADER)

    _add_center_bold(school_name.upper())
    _add_center_bold(config.get("exam_type", "Half Yearly").upper())
    _add_center_bold(subject.upper())
    _add_center_bold(f"SET - {paper_set}")

    # 3. Tabbed Rows
    def _add_tabbed_row(left_text, right_text):
        p = cell.add_paragraph()
        tab_stops = p.paragraph_format.tab_stops
        tab_stops.add_tab_stop(Cm(usable_width_cm - 0.2), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.SPACES)
        _bold_run(p, left_text, FONT_SIZE_HEADER)
        p.add_run("\t")
        _bold_run(p, right_text, FONT_SIZE_HEADER)

    _add_tabbed_row(f"STD: {grade}", f"MARKS: {total_marks}")
    _add_tabbed_row(f"DATE: {date_str}", f"TIME: {duration}")

    doc.add_paragraph() # spacer

    # ── General Instructions ─────────────────────────────────────────────────
    instr_head = doc.add_paragraph()
    _bold_run(instr_head, "General Instructions:", FONT_SIZE_INSTR)

    instructions = []
    # Build sections dynamically
    for sec in sections:
        attempt = int(sec.get("attemptCount") or sec.get("attempt_count") or sec["count"])
        count = int(sec["count"])
        if attempt < count:
            instructions.append(f"Section {sec['name']} contains {count} {sec['type'].lower()}, out of which any {attempt} are to be answered ({sec['marks']} marks each).")
        else:
            instructions.append(f"Section {sec['name']} contains {count} {sec['type'].lower()} of {sec['marks']} mark(s) each.")

    instructions.append(f"Time allowed is {duration}.")

    for i, line in enumerate(instructions):
        p = doc.add_paragraph()
        _normal_run(p, f"{i+1}. {line}", FONT_SIZE_INSTR)

    doc.add_paragraph() # spacer

    # ── Questions (Paragraph layout) ─────────────────────────────────────────
    q_num = 1
    for sec in sections:
        attempt = int(sec.get("attemptCount") or sec.get("attempt_count") or sec["count"])
        marks = int(sec["marks"])
        total_sec_marks = attempt * marks
        
        # Section Header
        p_hdr = doc.add_paragraph()
        p_hdr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _bold_run(p_hdr, f"SECTION {sec['name']} - {sec['type'].upper()} ({total_sec_marks} MARKS)", FONT_SIZE_BODY)
        
        # Sub-header
        p_sub = doc.add_paragraph()
        if attempt < int(sec["count"]):
            _normal_run(p_sub, f"Answer ANY {attempt} out of the following {sec['count']} questions. ({attempt} x {marks} = {total_sec_marks})", FONT_SIZE_BODY)
        else:
            _normal_run(p_sub, f"All questions are compulsory. ({attempt} x {marks} = {total_sec_marks})", FONT_SIZE_BODY)
            
        doc.add_paragraph() # spacer

        # Questions
        questions = sec.get("questions", [])
        for i in range(int(sec["count"])):
            if i < len(questions):
                q_raw = questions[i].get("text", "")
            else:
                q_raw = ""
            
            # Format nicely
            q_lines = _split_inline_options(q_raw.split("\n"))
            p_q = doc.add_paragraph()
            _bold_run(p_q, f"Q{q_num}. ", FONT_SIZE_BODY)
            
            if q_lines:
                first_line = re.sub(r"^(?:q\s*\d+[\.:\s]*|\d+[\.:\s]+)", "", q_lines[0], flags=re.IGNORECASE).strip()
                _normal_run(p_q, first_line, FONT_SIZE_BODY)
                for line in q_lines[1:]:
                    p_opt = doc.add_paragraph()
                    _normal_run(p_opt, f"   {line}", FONT_SIZE_BODY)
            
            q_num += 1
            doc.add_paragraph() # spacer after question

    # ── Save to bytes ─────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def _shuffle_sections(sections: list) -> list:
    """Return a deep copy of sections with questions shuffled within each section."""
    shuffled = []
    for sec in sections:
        s = dict(sec)
        qs = list(sec.get("questions", []))
        random.shuffle(qs)
        s["questions"] = qs
        shuffled.append(s)
    return shuffled


def get_section_preset(total_marks: int):
    """Return default section preset for given total marks (strips questions list)."""
    preset = SECTION_PRESETS.get(total_marks)
    if preset is None:
        # Build a sensible custom preset
        preset = _build_custom_preset(total_marks)
    return [dict(s) for s in preset]


def _build_custom_preset(total_marks: int) -> list:
    """Generate a balanced section breakdown for arbitrary total marks."""
    # Try to allocate proportionally
    base = [
        {"name": "A", "type": "Multiple Choice Questions",        "marks": 1},
        {"name": "B", "type": "Very Short Answer Type Questions", "marks": 2},
        {"name": "C", "type": "Short Answer Type Questions",      "marks": 3},
        {"name": "D", "type": "Case/Source-Based Questions",      "marks": 4},
        {"name": "E", "type": "Long Answer Type Questions",       "marks": 5},
    ]
    ratios = [0.25, 0.15, 0.25, 0.15, 0.20]
    sections = []
    remaining = total_marks
    for i, (sec, ratio) in enumerate(zip(base, ratios)):
        if i == len(base) - 1:
            count = max(1, remaining // sec["marks"])
        else:
            alloc = int(total_marks * ratio)
            count = max(1, alloc // sec["marks"])
        sec["count"] = count
        remaining -= count * sec["marks"]
        sections.append(sec)
    return sections

def generate_answer_key_paper(config: dict) -> bytes:
    doc = Document()

    school_name = config.get("school_name", "")
    grade       = config.get("grade", "")
    subject     = config.get("subject", "")
    paper_set   = config.get("paper_set", "")
    total_marks = config.get("total_marks", 0)
    duration    = config.get("duration", "")
    date_str    = config.get("date", "")
    sections    = config.get("sections", [])

    section = doc.sections[0]
    section.page_height = Cm(27.94)
    section.page_width  = Cm(21.59)
    section.top_margin    = Cm(1.75)
    section.bottom_margin = Cm(1.91)
    section.left_margin   = Cm(2.54)
    section.right_margin  = Cm(2.54)

    style = doc.styles["Normal"]
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after  = Pt(0)

    usable_width_cm = 21.59 - 2.54 - 2.54
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER

    # ── Header Box (1x1 Table) ───────────────────────────────────────────────
    header_table = doc.add_table(rows=1, cols=1)
    _set_table_border(header_table, "single")
    cell = header_table.cell(0, 0)
    cell.width = Cm(usable_width_cm)

    # 1. Logo
    logo_p = cell.add_paragraph()
    logo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if os.path.exists(LOGO_PATH):
        run = logo_p.add_run()
        run.add_picture(LOGO_PATH, height=Cm(1.8))
    else:
        run = logo_p.add_run("                                                           ")
        run.font.size = Emu(127000)

    # 2. School Name & Details
    def _add_center_bold(text):
        p = cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _bold_run(p, text, FONT_SIZE_HEADER)

    _add_center_bold(school_name.upper())
    _add_center_bold("ANSWER KEY")
    _add_center_bold(subject.upper())
    _add_center_bold(f"SET - {paper_set}")

    # 3. Tabbed Rows
    def _add_tabbed_row(left_text, right_text):
        p = cell.add_paragraph()
        tab_stops = p.paragraph_format.tab_stops
        tab_stops.add_tab_stop(Cm(usable_width_cm - 0.2), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.SPACES)
        _bold_run(p, left_text, FONT_SIZE_HEADER)
        p.add_run("	")
        _bold_run(p, right_text, FONT_SIZE_HEADER)

    _add_tabbed_row(f"STD: {grade}", f"MARKS: {total_marks}")
    _add_tabbed_row(f"DATE: {date_str}", f"TIME: {duration}")

    doc.add_paragraph() # spacer

    q_num = 1
    for sec in sections:
        p_hdr = doc.add_paragraph()
        p_hdr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _bold_run(p_hdr, f"SECTION {sec['name']} - {sec.get('type', 'QUESTIONS').upper()}", FONT_SIZE_BODY)
        doc.add_paragraph()
        
        questions = sec.get("questions", [])
        for i in range(int(sec.get("count", len(questions)))):
            if i < len(questions):
                q = questions[i]
                q_raw = q.get("text", "")
                ans_text = q.get("answer_text", "Answer not available.")
            else:
                q_raw = ""
                ans_text = "Answer not available."
                
            q_lines = _split_inline_options(q_raw.split("\n"))
            p_q = doc.add_paragraph()
            _bold_run(p_q, f"Q{q_num}. ", FONT_SIZE_BODY)
            
            sec_type_lower = sec.get("type", "").lower()
            sec_marks = int(sec.get("marks", 1))
            
            # A question is ONLY an MCQ if it carries 1 mark AND belongs to an MCQ/Objective/Assertion-Reason section
            is_mcq = (sec_marks == 1) and (
                any(t in sec_type_lower for t in ["multiple choice", "mcq", "objective", "assertion"]) or
                sec.get("name", "").upper() == "A"
            )
            
            if q_lines:
                first_line = re.sub(r"^(?:q\s*\d+[\.:\s]*|\d+[\.:\s]+)", "", q_lines[0], flags=re.IGNORECASE).strip()
                _normal_run(p_q, first_line, FONT_SIZE_BODY)
                
                if is_mcq:
                    # Extract the single correct option letter (a, b, c, or d)
                    correct_letter = _extract_ans_letter(ans_text)
                    
                    # Render each option line, splitting multi-option lines so ONLY the correct option run is bold!
                    for opt_l in q_lines[1:]:
                        _render_mcq_line_in_docx(doc, opt_l, correct_letter)
                        
                    # For MCQs: NEVER write Ans: below!
                else:
                    # Non-MCQ (Very Short, Short, Long Answer, Case Studies):
                    # Sub-parts like 1, 2, 3 or a, b, c are parts of the question, NEVER bold them!
                    for line in q_lines[1:]:
                        p_sub = doc.add_paragraph()
                        _normal_run(p_sub, f"   {line}", FONT_SIZE_BODY)
                        
                    # ALWAYS print the full theoretical/numerical answer below!
                    doc.add_paragraph()
                    p_ans = doc.add_paragraph()
                    _bold_run(p_ans, "Ans: ", FONT_SIZE_BODY)
                    _normal_run(p_ans, ans_text, FONT_SIZE_BODY)
            
            q_num += 1
            doc.add_paragraph()
            
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

def generate_blueprint_paper(config: dict, blueprint_data: dict) -> bytes:
    doc = Document()
    
    school_name = config.get("school_name", "PODAR WORLD SCHOOL VAPI")
    grade       = config.get("grade", "XII")
    subject     = config.get("subject", "ACCOUNTANCY")
    exam_type   = config.get("exam_type", "Term 1 Examination (2026-27)")
    total_marks = int(config.get("total_marks", 50))
    chapters    = blueprint_data.get("chapters", [])
    sections    = config.get("sections", [])
    
    section = doc.sections[0]
    is_landscape = len(chapters) > 3
    page_w_cm = 29.7 if is_landscape else 21.0
    if is_landscape:
        section.page_width  = Cm(29.7)
        section.page_height = Cm(21.0)
    else:
        section.page_width  = Cm(21.0)
        section.page_height = Cm(29.7)
        
    section.top_margin    = Cm(4.5)
    section.bottom_margin = Cm(1.27)
    section.left_margin   = Cm(1.27)
    section.right_margin  = Cm(1.27)
    section.header_distance = Cm(0.8)

    style = doc.styles["Normal"]
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after  = Pt(0)
    
    # ── Header on ALL pages (via section.header) ──
    header = section.header
    
    # 1. Logo
    logo_para = header.paragraphs[0]
    logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if os.path.exists(LOGO_PATH):
        run = logo_para.add_run()
        run.add_picture(LOGO_PATH, height=Cm(1.6))
    else:
        run = logo_para.add_run("                                                           ")
        run.font.size = Emu(127000)
    
    # 2. Header text
    p1 = header.add_paragraph()
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _bold_run(p1, school_name.upper(), FONT_SIZE_HEADER)
    
    p2 = header.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _bold_run(p2, exam_type, FONT_SIZE_HEADER)
    
    p3 = header.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _bold_run(p3, "BLUEPRINT", FONT_SIZE_HEADER)
    
    # 3. Std & Subject Row
    p_info = header.add_paragraph()
    usable_width_cm = page_w_cm - 2.54
    tab_stops = p_info.paragraph_format.tab_stops
    tab_stops.add_tab_stop(Cm(usable_width_cm), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.SPACES)
    
    _bold_run(p_info, f"Std: {grade}", FONT_SIZE_BODY)
    p_info.add_run("\t")
    _bold_run(p_info, f"Subject: {subject.upper()}", FONT_SIZE_BODY)
    
    # ── 4. Table 0: Blueprint Matrix ──
    cols = 2 + len(chapters)
    table = doc.add_table(rows=1, cols=cols)
    _set_table_border(table, "single")
    _repeat_table_header(table)
    
    # Header Row
    hdr = table.rows[0].cells
    hdr[0].text = "Topics / Types of questions"
    for i, ch in enumerate(chapters):
        hdr[1+i].text = ch.get("chapter_name", f"Chapter {i+1}")
    hdr[-1].text = "Total marks"
    
    for cell in hdr:
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.bold = True
                r.font.size = FONT_SIZE_BODY
                
    for sec in sections:
        sec_name = sec.get("name", "")
        sec_type = sec.get("type", "Questions")
        sec_marks_per_q = sec.get("marks", 1)
        sec_total_q = sec.get("count", 0)
        
        # Sub-header row: Section A (1 mark each)
        row_sec = table.add_row().cells
        mark_word = "mark" if sec_marks_per_q == 1 else "marks"
        row_sec[0].text = f"Section {sec_name} ({sec_marks_per_q} {mark_word} each)"
        for i in range(len(chapters)):
            row_sec[1+i].text = ""
        row_sec[-1].text = f"{sec_marks_per_q * sec_total_q} marks"
        
        for cell in [row_sec[0], row_sec[-1]]:
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.bold = True
                    r.font.size = FONT_SIZE_BODY
                    
        # Type row: Multiple Choice Questions
        row_data = table.add_row().cells
        row_data[0].text = sec_type
        
        for i, ch in enumerate(chapters):
            dist = ch.get("distribution", {})
            matched_q = 0
            target_sec_lower = f"section {sec_name.lower()}"
            for d_key, d_val in dist.items():
                d_key_lower = d_key.lower()
                if target_sec_lower in d_key_lower or d_key_lower.startswith(f"sec {sec_name.lower()}") or d_key_lower.startswith(sec_name.lower() + " "):
                    matched_q = d_val.get("count", 0)
                    break
                    
            if matched_q > 0:
                row_data[1+i].text = f"{matched_q}Q x {sec_marks_per_q}m = {matched_q * sec_marks_per_q}m"
            else:
                row_data[1+i].text = "---------"
                
        row_data[-1].text = f"{sec_marks_per_q * sec_total_q} marks"
        
        for cell in row_data:
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.size = FONT_SIZE_BODY

    # Total Marks Row
    row_total = table.add_row().cells
    row_total[0].text = "Total Marks"
    for i, ch in enumerate(chapters):
        row_total[1+i].text = f"{ch.get('total_chapter_marks', 0)} marks"
    row_total[-1].text = f"{total_marks} marks"
    
    for cell in row_total:
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.bold = True
                r.font.size = FONT_SIZE_BODY

    doc.add_paragraph()
    doc.add_paragraph()

    # ── 5. Table 1: Bloom's Taxonomy ──
    p_bloom = doc.add_paragraph()
    p_bloom.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _bold_run(p_bloom, "Bloom's Taxonomy", FONT_SIZE_HEADER)
    
    t_bloom = doc.add_table(rows=10, cols=6)
    t_bloom.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_border(t_bloom, "single")
    _repeat_table_header(t_bloom)
    
    # Calculate proportional distribution for Bloom's and Difficulty
    total = total_marks
    r_tot = round(total * 0.28)
    ap_tot = round(total * 0.16)
    an_tot = round(total * 0.08)
    u_tot = max(0, total - (r_tot + ap_tot + an_tot))

    e_tot = round(total * 0.28)
    d_tot = round(total * 0.20)
    av_tot = max(0, total - (e_tot + d_tot))

    def _split3(val, e_w, av_w, d_w, tot_w):
        v_e = round(val * e_w / tot_w)
        v_d = round(val * d_w / tot_w)
        v_av = max(0, val - v_e - v_d)
        return v_e, v_av, v_d

    r_e, r_av, r_d = _split3(r_tot, e_tot, av_tot, d_tot, total)
    u_e, u_av, u_d = _split3(u_tot, e_tot, av_tot, d_tot, total)
    ap_e, ap_av, ap_d = _split3(ap_tot, e_tot, av_tot, d_tot, total)
    an_e = max(0, e_tot - (r_e + u_e + ap_e))
    an_d = max(0, d_tot - (r_d + u_d + ap_d))
    an_av = max(0, an_tot - an_e - an_d)

    bloom_rows = [
        ["Type of Questions (\u2192)", "Easy - E", "Average - Av", "Difficult - D", "Total Marks", "Percentage"],
        ["Bloom's Objectives (\u2193)", "", "", "", "", ""],
        ["Remembering (R)", str(r_e), str(r_av), str(r_d), str(r_tot), f"{round(r_tot/total*100)}%"],
        ["Understanding (U)", str(u_e), str(u_av), str(u_d), str(u_tot), f"{round(u_tot/total*100)}%"],
        ["Applying (Ap)", str(ap_e), str(ap_av), str(ap_d), str(ap_tot), f"{round(ap_tot/total*100)}%"],
        ["Analyzing (An)", str(an_e), str(an_av), str(an_d), str(an_tot), f"{round(an_tot/total*100)}%"],
        ["Evaluating (Ev)", "0", "0", "0", "0", "0%"],
        ["Creating (C)", "0", "0", "0", "0", "0%"],
        ["Total", str(e_tot), str(av_tot), str(d_tot), str(total), "100%"],
        ["Percentage", f"{round(e_tot/total*100)}%", f"{round(av_tot/total*100)}%", f"{round(d_tot/total*100)}%", "", "100%"]
    ]

    for r_idx, r_data in enumerate(bloom_rows):
        row_c = t_bloom.rows[r_idx].cells
        is_hdr = r_idx in [0, 1, 8, 9]
        for c_idx, val in enumerate(r_data):
            row_c[c_idx].text = val
            p = row_c[c_idx].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                if is_hdr or c_idx == 0 or c_idx >= 4:
                    r.font.bold = True
                r.font.size = FONT_SIZE_BODY

    doc.add_paragraph()
    doc.add_paragraph()

    # ── 6. General Instructions ──
    p_gi = doc.add_paragraph()
    _bold_run(p_gi, "General Instructions", FONT_SIZE_HEADER)
    
    p_gi_sub = doc.add_paragraph()
    _bold_run(p_gi_sub, "Read the following instructions very carefully and strictly follow them:", FONT_SIZE_INSTR)
    
    total_q = sum(int(s.get("count", 0)) for s in sections)
    sec_names = [s.get("name", "") for s in sections]
    num_words = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX", 7: "SEVEN"}.get(len(sections), str(len(sections)))
    
    if len(sec_names) > 1:
        sec_names_str = ", ".join(sec_names[:-1]) + " and " + sec_names[-1]
    else:
        sec_names_str = sec_names[0] if sec_names else "A"
        
    p_q_tot = doc.add_paragraph()
    _normal_run(p_q_tot, f"This Question Paper contains {total_q} questions.", FONT_SIZE_INSTR)
    
    p_div = doc.add_paragraph()
    _normal_run(p_div, f"The Question Paper is divided into {num_words} sections - SECTION {sec_names_str}.", FONT_SIZE_INSTR)
    
    curr_q = 1
    for sec in sections:
        s_name = sec.get("name", "")
        s_type = sec.get("type", "Questions")
        s_marks = sec.get("marks", 1)
        s_count = int(sec.get("count", 0))
        if s_count == 0:
            continue
            
        mark_word = "mark" if s_marks == 1 else "marks"
        if s_count == 1:
            q_range_str = f"question number {curr_q} is a"
            plural_type = s_type.rstrip("s")
            p_sec = doc.add_paragraph()
            _normal_run(p_sec, f"In Section {s_name}, {q_range_str} {plural_type} carrying {s_marks} {mark_word}.", FONT_SIZE_INSTR)
        else:
            q_range_str = f"question numbers {curr_q} to {curr_q + s_count - 1} are"
            p_sec = doc.add_paragraph()
            _normal_run(p_sec, f"In Section {s_name}, {q_range_str} {s_type} carrying {s_marks} {mark_word} each.", FONT_SIZE_INSTR)
        curr_q += s_count
        
    p_all = doc.add_paragraph()
    _normal_run(p_all, "All questions are compulsory.", FONT_SIZE_INSTR)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()