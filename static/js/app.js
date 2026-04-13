function esc(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toast(message, type = "info") {
  const wrap = document.getElementById("toastWrap");
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = message;
  wrap.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 350);
  }, 3200);
}

function renderMd(raw) {
  let text = esc(raw);
  text = text.replace(/```([^\n]*)\n?([\s\S]*?)```/g, (_, _lang, code) => {
    const id = "cb" + Math.random().toString(36).slice(2, 8);
    return `<div class="code-wrap"><pre><code id="${id}">${code.trim()}</code></pre><button class="copy-btn" data-copy-target="${id}">Copy</button></div>`;
  });
  text = text.replace(/`([^`\n]+)`/g, '<span class="icode">$1</span>');
  text = text.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  text = text.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  text = text.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");
  text = text.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");
  text = text.replace(/^---$/gm, "<hr>");
  text = text.replace(/((?:^[*\-] .+(?:\n|$))+)/gm, block => {
    const items = block.trim().split("\n").map(line => `<li>${line.replace(/^[*\-] /, "")}</li>`).join("");
    return `<ul>${items}</ul>`;
  });
  text = text.replace(/((?:^\d+\. .+(?:\n|$))+)/gm, block => {
    const items = block.trim().split("\n").map(line => `<li>${line.replace(/^\d+\. /, "")}</li>`).join("");
    return `<ol>${items}</ol>`;
  });
  return text.split(/\n{2,}/).map(block => {
    const trimmed = block.trim();
    if (!trimmed) return "";
    if (/^<(h[1-3]|ul|ol|blockquote|hr|div)/.test(trimmed)) return trimmed;
    return `<p>${trimmed.replace(/\n/g, "<br>")}</p>`;
  }).join("");
}

const MOON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
const SUN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>';

let busy = false;

const themeBtn = document.getElementById("themeBtn");
const statusPill = document.getElementById("statusPill");
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const reindexBtn = document.getElementById("reindexBtn");
const indexStatus = document.getElementById("indexStatus");
const docList = document.getElementById("docList");
const docCount = document.getElementById("docCount");
const messagesScroll = document.getElementById("messagesScroll");
const msgsInner = document.getElementById("msgsInner");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");

function applyTheme(theme) {
  document.body.dataset.theme = theme;
  localStorage.setItem("cd-theme", theme);
  themeBtn.innerHTML = theme === "dark" ? SUN : MOON;
}

function toggleTheme() {
  applyTheme(document.body.dataset.theme === "dark" ? "light" : "dark");
}

function ficClass(name) {
  return ({ pdf: "pdf", docx: "docx", txt: "txt", md: "md" })[name.split(".").pop().toLowerCase()] || "file";
}

function ficLabel(name) {
  return ({ pdf: "PDF", docx: "DOC", txt: "TXT", md: "MD" })[name.split(".").pop().toLowerCase()] || "...";
}

function setInputHeight() {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 130) + "px";
}

function hideWelcome() {
  const welcome = document.getElementById("welcome");
  if (welcome) welcome.remove();
}

function scrollBottom() {
  messagesScroll.scrollTop = messagesScroll.scrollHeight;
}

function appendMsg(role, html, sources = []) {
  const row = document.createElement("div");
  row.className = "mrow " + role;
  const sourceMarkup = sources.length
    ? `<div class="sources"><span class="src-lbl">Sources</span>${sources.map(source => `<span class="src-tag">${esc(source)}</span>`).join("")}</div>`
    : "";
  row.innerHTML = `<div class="mavatar">${role === "user" ? "You" : "AI"}</div><div class="mbody"><div class="bubble">${html}${sourceMarkup}</div></div>`;
  msgsInner.appendChild(row);
  scrollBottom();
}

function showTyping() {
  const row = document.createElement("div");
  row.className = "mrow bot";
  row.id = "typingRow";
  row.innerHTML = '<div class="mavatar">AI</div><div class="mbody"><div class="bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div></div>';
  msgsInner.appendChild(row);
  scrollBottom();
}

function removeTyping() {
  const typingRow = document.getElementById("typingRow");
  if (typingRow) typingRow.remove();
}

function prefill(text) {
  chatInput.value = text;
  chatInput.focus();
  setInputHeight();
}

async function checkStatus() {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  dot.className = "sdot spin";
  text.textContent = "Checking...";

  try {
    const response = await fetch("/status");
    const data = await response.json();
    const backendMap = {
      tfidf: "TF-IDF",
      "sentence-transformers": "Embeddings",
      "not-built": "No Index",
      unknown: "?"
    };
    const backend = backendMap[data.retrieval_backend] || "?";

    if (data.connected && data.model_available) {
      dot.className = "sdot ok";
      text.textContent = `${data.model} · ${backend}`;
      return;
    }

    dot.className = "sdot err";
    text.textContent = "API key missing";
    toast("Set DEEPSEEK_API_KEY in Vercel environment variables.", "err");
  } catch (_error) {
    dot.className = "sdot err";
    text.textContent = "Connection error";
  }
}

async function loadDocs() {
  const response = await fetch("/documents");
  const data = await response.json();
  const files = data.files || [];
  docCount.textContent = files.length;

  if (!files.length) {
    docList.innerHTML = '<div class="doc-empty">No documents yet</div>';
    return;
  }

  docList.innerHTML = files.map(file => `
    <div class="doc-item">
      <div class="ficon ${ficClass(file)}">${ficLabel(file)}</div>
      <span class="doc-name" title="${esc(file)}">${esc(file)}</span>
      <button class="doc-del" type="button" data-filename="${esc(file)}" title="Remove">x</button>
    </div>
  `).join("");
}

async function deleteDoc(name) {
  if (!confirm(`Remove "${name}"?`)) return;
  const response = await fetch("/documents/" + encodeURIComponent(name), { method: "DELETE" });
  if (response.ok) {
    toast(name + " removed", "ok");
    loadDocs();
  } else {
    toast("Failed to remove file", "err");
  }
}

async function uploadFile(file) {
  const wrap = document.getElementById("upBarWrap");
  const bar = document.getElementById("upBar");
  wrap.style.display = "block";
  bar.style.width = "20%";

  const formData = new FormData();
  formData.append("file", file);

  try {
    bar.style.width = "65%";
    const response = await fetch("/upload", { method: "POST", body: formData });
    const data = await response.json();
    bar.style.width = "100%";
    if (response.ok) {
      toast(file.name + " uploaded", "ok");
      await loadDocs();
      indexStatus.textContent = "Rebuild the index to include the new file.";
      indexStatus.className = "idx-status";
    } else {
      toast(data.detail || "Upload failed", "err");
    }
  } catch (_error) {
    toast("Upload error", "err");
  }

  setTimeout(() => {
    wrap.style.display = "none";
    bar.style.width = "0";
  }, 700);
  fileInput.value = "";
}

async function reindex() {
  reindexBtn.disabled = true;
  reindexBtn.textContent = "Rebuilding...";
  indexStatus.textContent = "";
  indexStatus.className = "idx-status";

  try {
    const response = await fetch("/reindex", { method: "POST" });
    const data = await response.json();
    if (response.ok) {
      indexStatus.textContent = `Indexed ${data.chunks} sections`;
      indexStatus.className = "idx-status ok";
      toast(`Index rebuilt - ${data.chunks} sections`, "ok");
      checkStatus();
    } else {
      indexStatus.textContent = data.detail || "Indexing failed";
      indexStatus.className = "idx-status err";
      toast(data.detail || "Indexing failed", "err");
    }
  } catch (_error) {
    indexStatus.textContent = "Connection error";
    indexStatus.className = "idx-status err";
    toast("Reindex failed", "err");
  }

  reindexBtn.disabled = false;
  reindexBtn.textContent = "Rebuild Index";
}

async function sendMessage() {
  if (busy) return;

  const question = chatInput.value.trim();
  if (!question) return;

  hideWelcome();
  appendMsg("user", `<p>${esc(question)}</p>`);
  chatInput.value = "";
  setInputHeight();

  busy = true;
  sendBtn.disabled = true;
  showTyping();

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });
    const data = await response.json();
    removeTyping();
    if (!response.ok) {
      appendMsg("bot", `<p style="color:var(--err)">&#9888; ${esc(data.detail || "Something went wrong")}</p>`);
    } else {
      appendMsg("bot", renderMd(data.answer || "No answer generated."), data.sources || []);
    }
  } catch (_error) {
    removeTyping();
    appendMsg("bot", '<p style="color:var(--err)">&#9888; Network error. Is the server running?</p>');
  }

  busy = false;
  sendBtn.disabled = false;
  chatInput.focus();
}

themeBtn.addEventListener("click", toggleTheme);
statusPill.addEventListener("click", checkStatus);
reindexBtn.addEventListener("click", reindex);
sendBtn.addEventListener("click", sendMessage);

dropzone.addEventListener("dragover", event => {
  event.preventDefault();
  dropzone.classList.add("drag");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("drag");
});

dropzone.addEventListener("drop", event => {
  event.preventDefault();
  dropzone.classList.remove("drag");
  if (event.dataTransfer.files[0]) {
    uploadFile(event.dataTransfer.files[0]);
  }
});

fileInput.addEventListener("change", event => {
  if (event.target.files[0]) {
    uploadFile(event.target.files[0]);
  }
});

chatInput.addEventListener("input", setInputHeight);
chatInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

document.addEventListener("click", event => {
  const chip = event.target.closest("[data-prefill]");
  if (chip) {
    prefill(chip.dataset.prefill);
    return;
  }

  const deleteBtn = event.target.closest("[data-filename]");
  if (deleteBtn) {
    deleteDoc(deleteBtn.dataset.filename);
    return;
  }

  const copyBtn = event.target.closest("[data-copy-target]");
  if (copyBtn) {
    const target = document.getElementById(copyBtn.dataset.copyTarget);
    if (!target) return;
    navigator.clipboard.writeText(target.textContent).then(() => {
      copyBtn.textContent = "Copied!";
      setTimeout(() => {
        copyBtn.textContent = "Copy";
      }, 2000);
    });
  }
});

applyTheme(localStorage.getItem("cd-theme") || "light");
setInputHeight();
checkStatus();
loadDocs();
