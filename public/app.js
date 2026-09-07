/* ──────────────────────────────────────────────────────────────────────────
   app.js – Question Paper Generator (v2)
   ────────────────────────────────────────────────────────────────────────── */

// ─── State ───────────────────────────────────────────────────────────────────
let state = {
  currentStep: 1,
  totalMarks: 30,
  sections: [],
  mode: null,
  activeSection: 0
  // Each section: { name, type, marks, count, attemptCount, files:[], questions:[] }
};

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Marks buttons
  document.querySelectorAll(".mark-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".mark-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const marks = btn.dataset.marks;
      const customInput = document.getElementById("total_marks");
      if (marks === "custom") {
        customInput.hidden = false;
        customInput.focus();
        state.totalMarks = parseInt(customInput.value) || 30;
      } else {
        customInput.hidden = true;
        state.totalMarks = parseInt(marks);
        customInput.value = state.totalMarks;
      }
    });
  });

  document.getElementById("total_marks").addEventListener("input", e => {
    state.totalMarks = parseInt(e.target.value) || 0;
    updateMarksSummary();
  });
});

// ─── Step navigation ─────────────────────────────────────────────────────────
function goToStep(num) {
  if (num === 2 && !validateStep1()) return;
  if (num === 3) buildReview();

  document.querySelectorAll(".step-panel").forEach(p => p.classList.remove("active"));
  document.getElementById(`step-${num}`).classList.add("active");

  document.querySelectorAll(".step[id^='step-indicator-']").forEach((el, i) => {
    const sNum = i + 1;
    el.classList.remove("active", "done");
    if (sNum < num)      el.classList.add("done");
    else if (sNum === num) el.classList.add("active");
  });

  state.currentStep = num;
  if (num === 2) initStep2();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ─── Step 1 ──────────────────────────────────────────────────────────────────
function validateStep1() {
  if (!document.getElementById("grade").value.trim())   { showToast("Please enter Class/Grade", "error"); return false; }
  if (!document.getElementById("subject").value.trim()) { showToast("Please enter Subject", "error"); return false; }
  return true;
}

function startManualBuild() {
  if (!validateStep1()) return;
  state.mode = "manual";
  goToStep(2);
}

function startSmartImport() {
  if (!validateStep1()) return;
  state.mode = "smart";
  document.getElementById("bulk-upload-input").click();
}

// ─── Step 2: Init ─────────────────────────────────────────────────────────────
async function initStep2() {
  document.getElementById("target-marks").textContent = state.totalMarks;

  // Only load from API if sections haven't been customised yet
  if (state.sections.length === 0) {
    try {
      const res  = await fetch(`/api/sections?marks=${state.totalMarks}`);
      const data = await res.json();
      state.sections = data.sections.map(s => ({
        name: s.name, type: s.type, marks: s.marks,
        count: s.count, attemptCount: null,
        note: s.note || "", files: [], questions: []
      }));
    } catch {
      showToast("Could not load section presets", "error");
      state.sections = [];
    }
  }

  renderAllSections();
  updateMarksSummary();

  const isSmart = state.mode === "smart";
  document.getElementById("editor-mode-label").textContent = isSmart ? "Imported paper" : "Manual paper builder";
  document.getElementById("editor-title").textContent = isSmart ? "Review your imported paper" : "Edit your question paper";
  document.getElementById("editor-hint").textContent = isSmart
    ? "Questions have been grouped into sections. Select a section to review or refine it."
    : "Select a section to set its structure and add its questions.";
  const summary = document.getElementById("ai-summary");
  summary.hidden = !isSmart;
  if (isSmart) {
    const questionCount = state.sections.reduce((sum, sec) => sum + sec.questions.length, 0);
    document.getElementById("ai-summary-title").textContent = `${state.sections.length} section${state.sections.length === 1 ? "" : "s"} and ${questionCount} question${questionCount === 1 ? "" : "s"} imported`;
  }
}

// ─── Render all sections ──────────────────────────────────────────────────────
function renderAllSections() {
  const container = document.getElementById("sections-container");
  container.innerHTML = "";
  if (state.sections.length === 0) return;
  if (state.activeSection >= state.sections.length) state.activeSection = 0;
  renderPaperOutline();
  renderSection(state.activeSection);
}

function renderPaperOutline() {
  const nav = document.getElementById("section-nav");
  if (!nav) return;
  nav.innerHTML = state.sections.map((sec, idx) => {
    const active = idx === state.activeSection ? "active" : "";
    const count = sec.questions.length ? `${sec.questions.length}/${sec.count}` : `${sec.count} Qs`;
    return `<button type="button" class="section-nav-item ${active}" onclick="selectSection(${idx})">
      <span class="nav-letter">${escapeHtml(sec.name)}</span><span class="nav-section-name">${escapeHtml(sec.type)}</span><span class="nav-meta">${count}</span>
    </button>`;
  }).join("");
}

function selectSection(idx) {
  state.activeSection = idx;
  renderAllSections();
}

function renderSection(idx) {
  const sec = state.sections[idx];
  const template = document.getElementById("section-template");
  const clone = template.content.cloneNode(true);
  const card = clone.querySelector(".section-card-v2");

  card.dataset.secIdx = idx;

  // Editable label
  const labelInput = card.querySelector(".sc-label-input");
  labelInput.value = sec.name;
  labelInput.addEventListener("input", e => {
    state.sections[idx].name = e.target.value;
    renderPaperOutline();
  });

  // Editable title
  const titleInput = card.querySelector(".sc-title-input");
  titleInput.value = sec.type;
  titleInput.addEventListener("input", e => {
    state.sections[idx].type = e.target.value;
    renderPaperOutline();
  });

  // Marks input
  const marksInput = card.querySelector(".sc-marks-input");
  marksInput.value = sec.marks;
  marksInput.addEventListener("input", e => {
    state.sections[idx].marks = parseInt(e.target.value) || 1;
    updateSectionTotal(card, idx);
    updateMarksSummary();
  });

  // Count input
  const countInput = card.querySelector(".sc-count-input");
  countInput.value = sec.count;
  countInput.addEventListener("input", e => {
    state.sections[idx].count = parseInt(e.target.value) || 0;
    updateSectionTotal(card, idx);
    updateMarksSummary();
  });

  // Attempt input
  const attemptInput = card.querySelector(".sc-attempt-input");
  if (sec.attemptCount) attemptInput.value = sec.attemptCount;
  attemptInput.addEventListener("input", e => {
    const v = parseInt(e.target.value);
    state.sections[idx].attemptCount = isNaN(v) ? null : v;
    updateSectionTotal(card, idx);
    updateMarksSummary();
  });

  // Section total
  updateSectionTotal(card, idx);

  // Upload zone
  const zone = card.querySelector(".sc-upload-zone");
  const fileInput = card.querySelector(".sc-file-input");
  const label = zone.querySelector(".upload-link-sm");

  label.addEventListener("click", e => { e.stopPropagation(); fileInput.click(); });
  zone.addEventListener("click", () => fileInput.click());
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", e => {
    e.preventDefault(); zone.classList.remove("dragging");
    addFilesToSection(idx, Array.from(e.dataTransfer.files), card);
  });
  fileInput.addEventListener("change", () => {
    addFilesToSection(idx, Array.from(fileInput.files), card);
    fileInput.value = "";
  });

  // Render existing files
  renderFilePills(idx, card);

  // Render existing questions
  if (sec.questions.length > 0) renderSectionQuestions(idx, card);

  document.getElementById("sections-container").appendChild(card);
}

function updateSectionTotal(card, idx) {
  const sec = state.sections[idx];
  const effective = sec.attemptCount && sec.attemptCount < sec.count
    ? sec.attemptCount : sec.count;
  const total = effective * sec.marks;
  card.querySelector(".sc-section-total").textContent = `${total} marks`;
}

// ─── Add / Delete sections ────────────────────────────────────────────────────
function addSection() {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const usedNames = state.sections.map(s => s.name);
  let newName = "X";
  for (const l of letters) {
    if (!usedNames.includes(l)) { newName = l; break; }
  }
  state.sections.push({
    name: newName, type: "New Section", marks: 1,
    count: 5, attemptCount: null, note: "", files: [], questions: []
  });
  state.activeSection = state.sections.length - 1;
  renderAllSections();
  updateMarksSummary();
}

function deleteSection(btn) {
  const card = btn.closest(".section-card-v2");
  const idx = parseInt(card.dataset.secIdx);
  state.sections.splice(idx, 1);
  state.activeSection = Math.max(0, Math.min(state.activeSection, state.sections.length - 1));
  renderAllSections();
  updateMarksSummary();
}

// ─── Marks summary ────────────────────────────────────────────────────────────
function updateMarksSummary() {
  const target = state.totalMarks;
  const configured = state.sections.reduce((sum, s) => {
    const effective = s.attemptCount && s.attemptCount < s.count ? s.attemptCount : s.count;
    return sum + effective * s.marks;
  }, 0);

  document.getElementById("configured-marks").textContent = configured;
  document.getElementById("target-marks").textContent     = target;

  const pill = document.getElementById("marks-pill");
  pill.classList.remove("ok", "warn");
  if (configured === target) pill.classList.add("ok");
  else                        pill.classList.add("warn");

  // Also update each section's total display
  document.querySelectorAll(".section-card-v2").forEach(card => {
    const idx = parseInt(card.dataset.secIdx);
    if (!isNaN(idx) && state.sections[idx]) updateSectionTotal(card, idx);
  });
}

// ─── File management per section ──────────────────────────────────────────────
function addFilesToSection(idx, files, card) {
  const sec = state.sections[idx];
  files.forEach(f => {
    if (!sec.files.find(x => x.name === f.name && x.size === f.size)) {
      sec.files.push(f);
    }
  });
  renderFilePills(idx, card);
}

function renderFilePills(idx, card) {
  const sec = state.sections[idx];
  const pillsEl = card.querySelector(".sc-file-pills");
  pillsEl.innerHTML = sec.files.map((f, fi) => `
    <div class="file-pill">
      📄 ${escapeHtml(f.name)}
      <button onclick="removeFileFromSection(${idx}, ${fi}, this)">✕</button>
    </div>
  `).join("");
}

function removeFileFromSection(idx, fileIdx, btn) {
  state.sections[idx].files.splice(fileIdx, 1);
  const card = btn.closest(".section-card-v2");
  renderFilePills(idx, card);
}

// ─── Extract questions for a section ─────────────────────────────────────────
async function extractSectionQuestions(btn) {
  const card    = btn.closest(".section-card-v2");
  const idx     = parseInt(card.dataset.secIdx);
  const sec     = state.sections[idx];
  const paste   = card.querySelector(".sc-paste-input").value.trim();

  if (sec.files.length === 0 && !paste) {
    showToast("Upload files or paste text for this section first", "error");
    return;
  }

  btn.disabled = true;
  showLoader(`Analyzing Section ${sec.name}...`, "Extracting questions for this section.");

  try {
    let questions = [];
    const seen = new Set();

    // Upload files
    if (sec.files.length > 0) {
      const fd = new FormData();
      sec.files.forEach(f => fd.append("file", f));
      const res  = await fetch("/api/extract", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Extraction failed");
      (data.questions || []).forEach(q => {
        const t = q.text?.trim();
        if (t && !seen.has(t)) { seen.add(t); questions.push(q); }
      });
    }

    // Paste text
    if (paste) {
      const res  = await fetch("/api/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: paste })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Extraction failed");
      (data.questions || []).forEach(q => {
        const t = q.text?.trim();
        if (t && !seen.has(t)) { seen.add(t); questions.push(q); }
      });
    }

    // Merge with existing (don't overwrite)
    const existingTexts = new Set(sec.questions.map(q => q.text?.trim()));
    questions.forEach(q => {
      if (!existingTexts.has(q.text?.trim())) {
        sec.questions.push(q);
      }
    });

    renderSectionQuestions(idx, card);
    showToast(`Section ${sec.name}: extracted ${questions.length} question(s)`, "success");
  } catch (err) {
    showToast("Error: " + err.message, "error");
  } finally {
    btn.disabled = false;
    hideLoader();
  }
}

function renderSectionQuestions(idx, card) {
  const sec      = state.sections[idx];
  const listEl   = card.querySelector(".sc-questions-list");
  const itemsEl  = card.querySelector(".sc-q-items");
  const badge    = card.querySelector(".sc-q-badge");
  const neededEl = card.querySelector(".sc-q-needed");

  badge.textContent = sec.questions.length;
  neededEl.textContent = `${sec.count} needed`;

  itemsEl.innerHTML = sec.questions.map((q, qi) => `
    <div class="sc-q-item">
      <span class="sc-q-num">#${qi + 1}</span>
      <span class="sc-q-text">${escapeHtml(q.text || "")}</span>
      <button class="sc-q-remove" onclick="removeQuestion(${idx}, ${qi})" title="Remove">✕</button>
    </div>
  `).join("");

  listEl.hidden = false;
}

function removeQuestion(secIdx, qIdx) {
  state.sections[secIdx].questions.splice(qIdx, 1);
  
  // Auto-decrement the target count to match the new list size if it exceeds it
  if (state.sections[secIdx].count > state.sections[secIdx].questions.length) {
    state.sections[secIdx].count = state.sections[secIdx].questions.length;
  }
  
  const card = document.querySelector(`.section-card-v2[data-sec-idx="${secIdx}"]`);
  if (card) {
    const countInput = card.querySelector(".sc-count-input");
    if (countInput) countInput.value = state.sections[secIdx].count;
    renderSectionQuestions(secIdx, card);
  }
  updateMarksSummary();
}

// ─── Step 3: Review ───────────────────────────────────────────────────────────
function buildReview() {
  document.getElementById("rev-school").textContent   = document.getElementById("school_name").value;
  document.getElementById("rev-grade").textContent    = document.getElementById("grade").value;
  document.getElementById("rev-subject").textContent  = document.getElementById("subject").value;
  document.getElementById("rev-marks").textContent    = state.totalMarks + " marks";
  document.getElementById("rev-duration").textContent = document.getElementById("duration").value;
  document.getElementById("rev-date").textContent     = document.getElementById("date_str").value || "TBD";

  let globalQ = 1;
  const reviewDiv = document.getElementById("review-sections");

  reviewDiv.innerHTML = state.sections.map(sec => {
    const qs      = sec.questions.slice(0, sec.count);
    const needed  = sec.count;
    const attempt = sec.attemptCount && sec.attemptCount < sec.count ? sec.attemptCount : null;
    const effective = attempt || needed;
    const secTotal  = effective * sec.marks;

    let qHtml = "";
    if (qs.length === 0) {
      qHtml = `<div class="no-q-warning">⚠ No questions uploaded for this section. ${needed} needed.</div>`;
    } else {
      qHtml = `<div class="review-q-list">` +
        qs.map((q, i) => `
          <div class="review-q-item">
            <span class="review-q-num">${globalQ + i}</span>
            <span class="review-q-text">${escapeHtml(q.text || "")}</span>
            <span class="review-q-marks">[${sec.marks}]</span>
          </div>
        `).join("") +
      `</div>`;
      if (qs.length < needed) {
        qHtml += `<div class="no-q-warning" style="margin:.5rem 1rem">⚠ ${needed - qs.length} more question(s) needed.</div>`;
      }
    }

    globalQ += needed;

    const attemptBadge = attempt
      ? `<span class="attempt-badge">Attempt any ${attempt}</span>`
      : "";

    return `
      <div class="review-section">
        <div class="review-section-header">
          <div class="section-badge" style="width:30px;height:30px;background:var(--primary);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.82rem;flex-shrink:0">${escapeHtml(sec.name)}</div>
          <h4>Section ${escapeHtml(sec.name)} – ${escapeHtml(sec.type)}</h4>
          ${attemptBadge}
          <span class="mark-info">${needed} Qs × ${sec.marks}m = ${secTotal} marks</span>
        </div>
        ${qHtml}
      </div>
    `;
  }).join("");
}

// ─── Generate ─────────────────────────────────────────────────────────────────
async function generatePaper() {
  const target = state.totalMarks;
  const configured = state.sections.reduce((sum, s) => {
    const effective = s.attemptCount && s.attemptCount < s.count ? s.attemptCount : s.count;
    return sum + (effective * s.marks);
  }, 0);

  if (configured > target) {
    showToast(`Error: The paper totals ${configured} marks, which exceeds your target of ${target} marks. Please adjust the section counts or attempt limits below.`, "error");
    return;
  }
  if (configured < target) {
    showToast(`Warning: The paper only totals ${configured} marks, but your target is ${target}. Proceeding anyway.`, "success");
  }

  showLoader("Generating Document...", "Compiling your question paper into a Word document.");
  const generateSetB = document.getElementById("generate-set-b").checked;

  const sectionsPayload = state.sections.map(sec => ({
    name:         sec.name,
    type:         sec.type,
    marks:        sec.marks,
    count:        sec.count,
    attemptCount: sec.attemptCount || null,
    note:         sec.note || "",
    questions:    sec.questions.slice(0, sec.count).map(q => ({ text: q.text, type: q.type }))
  }));

  const config = {
    school_name:    document.getElementById("school_name").value.trim(),
    grade:          document.getElementById("grade").value.trim(),
    subject:        document.getElementById("subject").value.trim(),
    exam_type:      document.getElementById("exam_type").value.trim() || "Half Yearly",
    paper_set:      "A",
    total_marks:    state.totalMarks,
    duration:       document.getElementById("duration").value.trim(),
    date:           document.getElementById("date_str").value.trim(),
    sections:       sectionsPayload,
    generate_set_b: false
  };

  document.getElementById("generate-btn").disabled = true;
  document.getElementById("generate-status").hidden = false;
  document.getElementById("generate-success").hidden = true;

  try {
    const endpoint = generateSetB ? "/api/generate-both" : "/api/generate";
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || "Generation failed");
    }

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    const cd   = res.headers.get("Content-Disposition") || "";
    const fnM  = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    a.download = fnM ? fnM[1].replace(/['"]/g, "") : "question_paper.docx";
    a.href = url;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    document.getElementById("generate-status").hidden = true;
    document.getElementById("generate-success").hidden = false;
    document.getElementById("post-generate-actions").hidden = false;
    showToast("Question paper generated successfully!", "success");
  } catch (err) {
    showToast("Error: " + err.message, "error");
  } finally {
    document.getElementById("generate-status").hidden = true;
    document.getElementById("generate-btn").disabled = false;
    hideLoader();
  }
}

// ─── Reset ────────────────────────────────────────────────────────────────────
function resetApp() {
  state = { currentStep: 1, totalMarks: 30, sections: [], mode: null, activeSection: 0 };
  document.getElementById("grade").value   = "";
  document.getElementById("subject").value = "";
  document.getElementById("generate-success").hidden = true;
  document.getElementById("post-generate-actions").hidden = true;
  document.getElementById("generate-btn").disabled = false;
  goToStep(1);
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showToast(msg, type = "") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0"; toast.style.transition = "opacity .3s";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// --- BULK UPLOAD FULL PAPER ---
async function handleBulkUpload(input) {
  if (!input.files || input.files.length === 0) return;
  
  const file = input.files[0];
  showLoader("Analyzing Full Paper...", "Extracting sections, marks, and questions. This might take a moment.");
  
  const fd = new FormData();
  fd.append("file", file);
  
  try {
    const res = await fetch("/api/extract", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Extraction failed");
    
    const questions = data.questions || [];
    if (questions.length === 0) {
      showToast("No questions found in the document.", "error");
      return;
    }
    
    // Group questions by section
    const bySection = {};
    questions.forEach(q => {
      const secName = q.section ? String(q.section).trim() : "A";
      if (!bySection[secName]) bySection[secName] = [];
      bySection[secName].push(q);
    });
    
    // Clear current sections and build new ones
    state.sections = [];
    
    Object.keys(bySection).sort().forEach(secName => {
      const qs = bySection[secName];
      // Try to determine marks from the most common marks value in this section
      const marksCounts = {};
      qs.forEach(q => {
        const m = q.marks || 1;
        marksCounts[m] = (marksCounts[m] || 0) + 1;
      });
      let bestMarks = 1;
      let maxCount = 0;
      for (const m in marksCounts) {
        if (marksCounts[m] > maxCount) {
          maxCount = marksCounts[m];
          bestMarks = parseInt(m);
        }
      }
      
      let guessedType = "Questions";
      const sName = secName.toUpperCase();
      if (sName === "A" || bestMarks === 1) guessedType = "Multiple Choice Questions";
      else if (sName === "B" || bestMarks === 2) guessedType = "Very Short Answer Type Questions";
      else if (sName === "C" || bestMarks === 3) guessedType = "Short Answer Type Questions";
      else if (sName === "D" || bestMarks >= 4) guessedType = "Long Answer Type Questions";

      state.sections.push({
        name: secName,
        type: guessedType,
        marks: bestMarks,
        count: qs.length,
        attemptCount: "",
        note: "",
        files: [],
        questions: qs
      });
    });
    
    state.activeSection = 0;
    state.mode = "smart";
    goToStep(2);
    renderAllSections();
    updateMarksSummary();
    showToast(`Successfully extracted ${questions.length} questions across ${state.sections.length} sections!`, "success");
  } catch (err) {
    showToast("Error processing file: " + err.message, "error");
  } finally {
    input.value = ""; // reset
    hideLoader();
  }
}

// --- LOADER HELPERS ---
function showLoader(title = "Analyzing Paper...", subtitle = "Our AI is extracting sections and questions. This might take a moment.") {
  const loader = document.getElementById("global-loader");
  if (!loader) return;
  document.getElementById("gl-title").innerText = title;
  document.getElementById("gl-subtitle").innerText = subtitle;
  loader.classList.add("show");
}

function hideLoader() {
  const loader = document.getElementById("global-loader");
  if (loader) loader.classList.remove("show");
}

// ─── Generate Answer Key ───────────────────────────────────────────────────────
async function generateAnswerKey() {
  const target = state.totalMarks;
  const configured = state.sections.reduce((sum, s) => {
    const effective = s.attemptCount && s.attemptCount < s.count ? s.attemptCount : s.count;
    return sum + (effective * s.marks);
  }, 0);

  if (configured > target) {
    showToast(`Error: The paper totals ${configured} marks, which exceeds your target of ${target} marks. Please adjust the section counts or attempt limits below.`, "error");
    return;
  }

  showLoader("Solving Paper...", "Our AI is analyzing your paper and generating the Answer Key. This may take up to a minute.");

  const sectionsPayload = state.sections.map(sec => ({
    name:         sec.name,
    type:         sec.type,
    marks:        sec.marks,
    count:        sec.count,
    attemptCount: sec.attemptCount || null,
    note:         sec.note || "",
    questions:    sec.questions.slice(0, sec.count).map(q => ({
      text: q.text || "",
      type: q.type || "unknown"
    }))
  }));

  const config = {
    school_name:    document.getElementById("school_name").value.trim(),
    grade:          document.getElementById("grade").value.trim(),
    subject:        document.getElementById("subject").value.trim(),
    exam_type:      document.getElementById("exam_type").value.trim() || "Half Yearly",
    paper_set:      "A",
    total_marks:    state.totalMarks,
    duration:       document.getElementById("duration").value.trim(),
    date:           document.getElementById("date_str").value.trim(),
    sections:       sectionsPayload,
    generate_set_b: document.getElementById("generate-set-b").checked
  };

  document.getElementById("generate-btn").disabled = true;
  document.getElementById("generate-ans-btn").disabled = true;

  try {
    const res = await fetch("/api/generate-answer-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || "Failed to generate answer key");
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    
    // Create an anchor to trigger download
    const a = document.createElement("a");
    a.href = url;
    
    // Extract filename from Content-Disposition if possible
    const disp = res.headers.get("Content-Disposition");
    let filename = "Answer_Key.docx";
    if (disp && disp.includes("filename=")) {
      filename = disp.split("filename=")[1].replace(/"/g, "");
    }
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showToast("Answer Key generated successfully!", "success");

  } catch (err) {
    showToast("Error generating answer key: " + err.message, "error");
  } finally {
    document.getElementById("generate-btn").disabled = false;
    document.getElementById("generate-ans-btn").disabled = false;
    hideLoader();
  }
}

// ─── Blueprint Generation ──────────────────────────────────────────────────────
function openBlueprintModal() {
  document.getElementById("blueprint-text").value = "";
  const fileInput = document.getElementById("blueprint-file");
  if (fileInput) fileInput.value = "";
  const listEl = document.getElementById("blueprint-file-list");
  if (listEl) {
    listEl.innerHTML = "";
    listEl.hidden = true;
  }
  const labelEl = document.getElementById("blueprint-upload-label");
  if (labelEl) labelEl.textContent = "Upload File(s) (PDF, DOCX, Images)";
  document.getElementById("blueprint-modal").hidden = false;
}

function clearBlueprintFiles() {
  const fileInput = document.getElementById("blueprint-file");
  if (fileInput) fileInput.value = "";
  const listEl = document.getElementById("blueprint-file-list");
  if (listEl) {
    listEl.innerHTML = "";
    listEl.hidden = true;
  }
  const labelEl = document.getElementById("blueprint-upload-label");
  if (labelEl) labelEl.textContent = "Upload File(s) (PDF, DOCX, Images)";
}

document.addEventListener("DOMContentLoaded", () => {
  const bpFileInput = document.getElementById("blueprint-file");
  if (bpFileInput) {
    bpFileInput.addEventListener("change", (e) => {
      const files = Array.from(e.target.files || []);
      const listEl = document.getElementById("blueprint-file-list");
      const labelEl = document.getElementById("blueprint-upload-label");
      if (!listEl) return;
      if (files.length === 0) {
        listEl.innerHTML = "";
        listEl.hidden = true;
        if (labelEl) labelEl.textContent = "Upload File(s) (PDF, DOCX, Images)";
        return;
      }
      listEl.hidden = false;
      if (labelEl) labelEl.textContent = `${files.length} file(s) selected`;
      listEl.innerHTML = `
        <div style="display:flex; flex-wrap:wrap; gap:0.4rem; align-items:center;">
          ${files.map(f => `<span style="background:var(--bg-card); border:1px solid var(--border); padding:0.25rem 0.5rem; border-radius:4px; font-size:0.8rem; color:var(--text-main);">📎 ${escapeHtml(f.name)} (${(f.size/1024).toFixed(0)}KB)</span>`).join("")}
          <button type="button" style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:0.75rem; text-decoration:underline; padding:0.2rem;" onclick="clearBlueprintFiles()">Clear</button>
        </div>
      `;
    });
  }
});

async function submitBlueprint() {
  document.getElementById("blueprint-modal").hidden = true;
  showLoader("Generating Blueprint...", "Analyzing your syllabus and mapping chapters to the question paper distribution.");
  
  const textVal = document.getElementById("blueprint-text").value.trim();
  const fileInput = document.getElementById("blueprint-file");
  const files = Array.from(fileInput.files || []);
  
  try {
    const sectionsPayload = state.sections.map(sec => ({
      name:         sec.name,
      type:         sec.type,
      marks:        sec.marks,
      count:        sec.count,
      attemptCount: sec.attemptCount || null,
      note:         sec.note || "",
      questions:    sec.questions.slice(0, sec.count).map(q => ({ text: q.text, type: q.type }))
    }));

    const fullConfig = {
      school_name:  document.getElementById("school_name")?.value.trim() || "PODAR WORLD SCHOOL VAPI",
      grade:        document.getElementById("grade")?.value.trim() || "XII",
      subject:      document.getElementById("subject")?.value.trim() || "ACCOUNTANCY",
      exam_type:    document.getElementById("exam_type")?.value.trim() || "Half Yearly",
      total_marks:  state.totalMarks,
      duration:     document.getElementById("duration")?.value.trim() || "3 Hours",
      date:         document.getElementById("date_str")?.value.trim() || "",
      sections:     sectionsPayload
    };

    const formData = new FormData();
    formData.append("config", JSON.stringify(fullConfig));
    
    if (files.length > 0) {
      files.forEach(f => formData.append("files", f));
      if (textVal) formData.append("text", textVal);
    } else if (textVal) {
      formData.append("text", textVal);
    } else {
      throw new Error("Please upload file(s) or paste the chapters text.");
    }
    
    const res = await fetch("/api/generate-blueprint", {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || "Failed to generate blueprint");
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement("a");
    a.href = url;
    
    const disp = res.headers.get("Content-Disposition");
    let filename = "Blueprint.docx";
    if (disp && disp.includes("filename=")) {
      filename = disp.split("filename=")[1].replace(/"/g, "");
    }
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showToast("Blueprint generated successfully!", "success");

  } catch (err) {
    showToast("Error generating blueprint: " + err.message, "error");
  } finally {
    hideLoader();
  }
}
