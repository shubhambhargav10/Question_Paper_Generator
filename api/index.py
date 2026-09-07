"""
index.py – Flask app for Podar World School Question Paper Generator.
Runs locally (python api/index.py) and deploys to Vercel.
"""

import os
import json
import base64
from flask import Flask, request, jsonify, send_file, send_from_directory
from dotenv import load_dotenv
import io

load_dotenv()

app = Flask(__name__, static_folder=None)

# ── Paths & sys.path ──────────────────────────────────────────────────────────
import sys
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR     = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

PUBLIC_DIR  = os.path.join(BASE_DIR, "public")
ASSETS_DIR  = os.path.join(BASE_DIR, "assets")


# ── Static frontend ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(PUBLIC_DIR, filename)


# ── API: Get section preset ───────────────────────────────────────────────────

@app.route("/api/sections", methods=["GET"])
def get_sections():
    """Return default section configuration for given total marks."""
    from generator import get_section_preset
    try:
        total_marks = int(request.args.get("marks", 50))
        sections = get_section_preset(total_marks)
        return jsonify({"sections": sections, "total_marks": total_marks})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── API: Extract questions ────────────────────────────────────────────────────

@app.route("/api/extract", methods=["POST"])
def extract():
    """
    Accepts multipart file upload OR JSON with base64 data.
    Returns extracted questions as JSON list.
    """
    from extractor import extract_questions, extract_from_text

    try:
        # Multipart file upload
        if request.files:
            questions = []
            seen = set()
            for key in request.files:
                f = request.files[key]
                file_bytes = f.read()
                filename   = f.filename or "upload.bin"
                mime       = f.content_type or "application/octet-stream"
                qs = extract_questions(file_bytes, filename, mime)
                for q in qs:
                    t = q.get("text", "").strip()
                    if t and t not in seen:
                        seen.add(t)
                        questions.append(q)
            return jsonify({"questions": questions})

        # JSON body with text or base64
        data = request.get_json(force=True)
        if "text" in data:
            questions = extract_from_text(data["text"])
            return jsonify({"questions": questions})

        if "files" in data:
            questions = []
            seen = set()
            for fdata in data["files"]:
                filename   = fdata.get("name", "upload.bin")
                mime       = fdata.get("mime", "application/octet-stream")
                b64        = fdata.get("data", "")
                file_bytes = base64.b64decode(b64)
                qs = extract_questions(file_bytes, filename, mime)
                for q in qs:
                    t = q.get("text", "").strip()
                    if t and t not in seen:
                        seen.add(t)
                        questions.append(q)
            return jsonify({"questions": questions})

        return jsonify({"error": "No files or text provided"}), 400

    except ValueError as ve:
        return jsonify({"error": str(ve), "hint": "Make sure GEMINI_API_KEY is set"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Generate question paper ──────────────────────────────────────────────

@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Accepts full paper config + questions.
    Returns .docx file for download.

    Body (JSON):
    {
      "school_name": "PODAR WORLD SCHOOL VAPI",
      "grade": "XI",
      "subject": "ECONOMICS",
      "paper_set": "A",
      "total_marks": 50,
      "duration": "2 hrs 10 min",
      "date": ".07.2026",
      "sections": [
        {
          "name": "A",
          "type": "Multiple Choice Questions",
          "marks": 1,
          "count": 16,
          "questions": [
            {"text": "Question text here...", "type": "MCQ"}
          ]
        },
        ...
      ]
    }
    """
    from generator import generate_question_paper

    try:
        config = request.get_json(force=True)
        if not config:
            return jsonify({"error": "No config provided"}), 400

        docx_bytes = generate_question_paper(config)

        grade     = config.get("grade", "XI")
        subject   = config.get("subject", "ECONOMICS").replace(" ", "_")
        set_label = config.get("paper_set", "A").upper()
        marks     = config.get("total_marks", 50)
        filename  = f"Question_Paper_{grade}_{subject}_SET{set_label}_{marks}Marks.docx"

        return send_file(
            io.BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Generate both Set A and Set B ───────────────────────────────────────

@app.route("/api/generate-both", methods=["POST"])
def generate_both():
    """
    Generates Set A and Set B, returns both as base64-encoded docx strings.
    """
    from generator import generate_question_paper
    import zipfile

    try:
        config = request.get_json(force=True)

        # Set A
        config_a = dict(config)
        config_a["paper_set"] = "A"
        config_a["generate_set_b"] = False
        docx_a = generate_question_paper(config_a)

        # Set B (shuffled)
        config_b = dict(config)
        config_b["paper_set"] = "B"
        config_b["generate_set_b"] = True
        docx_b = generate_question_paper(config_b)

        grade   = config.get("grade", "XI")
        subject = config.get("subject", "ECONOMICS").replace(" ", "_")
        marks   = config.get("total_marks", 50)

        # Package into a zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"Question_Paper_{grade}_{subject}_SETA_{marks}Marks.docx", docx_a)
            zf.writestr(f"Question_Paper_{grade}_{subject}_SETB_{marks}Marks.docx", docx_b)
        zip_buf.seek(0)

        zip_name = f"Question_Paper_{grade}_{subject}_{marks}Marks_SetA_SetB.zip"
        return send_file(
            zip_buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_name,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Generate Answer Key ───────────────────────────────────────────────

@app.route("/api/generate-answer-key", methods=["POST"])
def generate_answer_key():
    from generator import generate_answer_key_paper, _shuffle_sections
    from extractor import generate_solutions
    import zipfile

    try:
        config = request.get_json(force=True)
        if not config:
            return jsonify({"error": "No config provided"}), 400

        generate_b = config.get("generate_set_b", False)
        
        # We need to solve the sections first. Since Gemini calls cost quota,
        # we solve Set A, and then for Set B we just shuffle the already-solved sections!
        solved_config = generate_solutions(dict(config))
        
        if not generate_b:
            docx_bytes = generate_answer_key_paper(solved_config)
            grade     = solved_config.get("grade", "XI")
            subject   = solved_config.get("subject", "ECONOMICS").replace(" ", "_")
            set_label = solved_config.get("paper_set", "A").upper()
            marks     = solved_config.get("total_marks", 50)
            filename  = f"Answer_Key_{grade}_{subject}_SET{set_label}_{marks}Marks.docx"

            return send_file(
                io.BytesIO(docx_bytes),
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                as_attachment=True,
                download_name=filename,
            )
        else:
            # Generate BOTH Set A and Set B Answer Keys
            config_a = dict(solved_config)
            config_a["paper_set"] = "A"
            docx_a = generate_answer_key_paper(config_a)
            
            config_b = dict(solved_config)
            config_b["paper_set"] = "B"
            # Shuffle the solved sections
            config_b["sections"] = _shuffle_sections(config_b["sections"])
            docx_b = generate_answer_key_paper(config_b)
            
            grade   = config.get("grade", "XI")
            subject = config.get("subject", "ECONOMICS").replace(" ", "_")
            marks   = config.get("total_marks", 50)
            
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"Answer_Key_{grade}_{subject}_SETA_{marks}Marks.docx", docx_a)
                zf.writestr(f"Answer_Key_{grade}_{subject}_SETB_{marks}Marks.docx", docx_b)
            zip_buf.seek(0)
            
            zip_name = f"Answer_Key_{grade}_{subject}_{marks}Marks_SetA_SetB.zip"
            return send_file(
                zip_buf,
                mimetype="application/zip",
                as_attachment=True,
                download_name=zip_name,
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ── API: Generate Blueprint ───────────────────────────────────────────────

@app.route("/api/generate-blueprint", methods=["POST"])
def generate_blueprint():
    from generator import generate_blueprint_paper
    from extractor import extract_blueprint_mapping
    
    try:
        config_str = request.form.get("config")
        if not config_str:
            return jsonify({"error": "No config provided"}), 400
        config = json.loads(config_str)
        
        portion_text = request.form.get("text", "")
        last_extract_err = None
        
        # Collect all uploaded files across all field names (files, file, etc.)
        uploaded_files = []
        for key in request.files:
            for f in request.files.getlist(key):
                if f and f.filename and f not in uploaded_files:
                    uploaded_files.append(f)

        print(f"generate_blueprint: text length={len(portion_text)}, files count={len(uploaded_files)}")

        for f in uploaded_files:
            file_bytes = f.read()
            if not file_bytes:
                continue
            filename = (f.filename or "").lower()
            mime = f.content_type or ""
            ext = os.path.splitext(filename)[1].lower()
            ext_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".pdf": "application/pdf",
            }
            clean_mime = ext_map.get(ext, mime or "image/jpeg")
            if clean_mime == "application/octet-stream":
                clean_mime = ext_map.get(ext, "image/jpeg")

            # Direct extraction for docx, pdf, txt (no Gemini API quota used!)
            extracted_from_file = ""
            if filename.endswith(".docx"):
                try:
                    import docx
                    d = docx.Document(io.BytesIO(file_bytes))
                    extracted_from_file = "\n".join([p.text for p in d.paragraphs if p.text.strip()])
                except Exception as de:
                    print(f"Direct docx extract failed: {de}")

            elif filename.endswith(".pdf"):
                try:
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    pages_text = [page.extract_text() for page in reader.pages if page.extract_text()]
                    extracted_from_file = "\n".join(pages_text)
                except Exception as pe:
                    print(f"Direct pdf extract failed: {pe}")

                # If scanned PDF (no selectable text), convert pages to images
                if not extracted_from_file.strip():
                    try:
                        import fitz
                        doc = fitz.open(stream=file_bytes, filetype="pdf")
                        ocr_parts = []
                        try:
                            from extractor import _call_gemini_with_fallback
                        except ImportError:
                            from api.extractor import _call_gemini_with_fallback
                        for page_num in range(min(len(doc), 5)):
                            pix = doc[page_num].get_pixmap(matrix=fitz.Matrix(150/72, 150/72))
                            img_part = {"mime_type": "image/jpeg", "data": pix.tobytes("jpeg")}
                            resp = _call_gemini_with_fallback(
                                "Extract all syllabus chapters, units, and topic titles from this page as plain text.",
                                parts=[img_part]
                            )
                            if resp and resp.text:
                                ocr_parts.append(resp.text)
                        extracted_from_file = "\n".join(ocr_parts)
                    except Exception as fe:
                        print(f"PDF OCR extract failed: {fe}")

            elif filename.endswith(".txt"):
                extracted_from_file = file_bytes.decode("utf-8", errors="ignore")

            # Fallback to Gemini Vision with automatic model failover (for images/photos)
            if not extracted_from_file.strip():
                try:
                    try:
                        from extractor import _call_gemini_with_fallback
                    except ImportError:
                        from api.extractor import _call_gemini_with_fallback
                    img_part = {"mime_type": clean_mime, "data": file_bytes}
                    response = _call_gemini_with_fallback(
                        "Extract all syllabus chapters, units, and topic titles from this document/image as a clean list of chapter names.",
                        parts=[img_part]
                    )
                    extracted_from_file = response.text if response else ""
                except Exception as ge:
                    last_extract_err = str(ge)
                    print(f"Gemini image extract failed: {ge}")

            if extracted_from_file.strip():
                portion_text += "\n" + extracted_from_file.strip()

        if not portion_text:
            return jsonify({
                "error": "No syllabus text or file could be extracted",
                "details": f"files_received={[f.filename for f in uploaded_files]}, last_error={last_extract_err}"
            }), 400

        # Pass config and portion_text to extractor to map chapters to questions
        mapped_blueprint = extract_blueprint_mapping(config, portion_text)

        # Generate the docx
        docx_bytes = generate_blueprint_paper(config, mapped_blueprint)

        grade     = config.get("grade", "XII")
        subject   = config.get("subject", "ACCOUNTANCY").replace(" ", "_")
        filename  = f"Blueprint_{grade}_{subject}.docx"

        return send_file(
            io.BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Health check ──────────────────────────────────────────────────────────────


@app.route("/api/health", methods=["GET"])
def health():
    gemini_key_set = bool(os.environ.get("GEMINI_API_KEY", ""))
    return jsonify({
        "status": "ok",
        "gemini_api_key_set": gemini_key_set,
    })


# ── Run locally ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Starting Question Paper Generator on http://localhost:{port}")
    app.run(host="0.0.0.0", debug=True, port=port)
