const state = {
  documents: [],
  selectedIds: [],
  sessionId: null,
};

const docListEl = document.getElementById("docList");
const chatLogEl = document.getElementById("chatLog");

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  chatLogEl.appendChild(div);
  chatLogEl.scrollTop = chatLogEl.scrollHeight;
}

function stripModelCitations(answer) {
  const marker = "\nCitations:";
  const idx = answer.indexOf(marker);
  if (idx === -1) return answer.trim();
  return answer.slice(0, idx).trim();
}

function renderCitations(citations) {
  if (!citations || citations.length === 0) return;

  const lines = ["Citations:"];
  citations.forEach((citation) => {
    lines.push(`- "${citation.quote}" | Source: ${citation.source} | Location: ${citation.location}`);
  });
  addMessage("assistant", lines.join("\n"));
}

async function refreshDocuments() {
  await refreshDocumentsWithRetry(2);
}

async function refreshDocumentsWithRetry(retriesLeft) {
  try {
    const res = await fetch("/api/documents", { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    state.documents = data.documents || [];
    state.selectedIds = state.documents.filter((d) => d.is_selected).map((d) => d.id);
    renderDocuments();
  } catch (err) {
    if (retriesLeft > 0) {
      setTimeout(() => {
        refreshDocumentsWithRetry(retriesLeft - 1);
      }, 700);
      return;
    }
    addMessage("assistant", "Could not refresh resources. Please reload the page.");
  }
}

function renderDocuments() {
  docListEl.innerHTML = "";
  state.documents.forEach((doc) => {
    const item = document.createElement("div");
    item.className = "doc-item";

    const main = document.createElement("div");
    main.className = "doc-main";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!doc.is_selected;
    cb.addEventListener("change", async () => {
      await fetch(`/api/documents/${doc.id}/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected: cb.checked }),
      });
      await refreshDocuments();
    });

    const text = document.createElement("span");
    text.textContent = `${doc.name} (${doc.source_type})`;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "delete-btn";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", async () => {
      const ok = confirm(`Remove resource: ${doc.name}?`);
      if (!ok) return;

      const res = await fetch(`/api/documents/${doc.id}`, {
        method: "DELETE",
      });
      const data = await res.json();

      if (!res.ok) {
        addMessage("assistant", `Delete failed: ${data.detail || "Unknown error"}`);
        return;
      }

      addMessage("assistant", `Removed ${data.name}.`);
      await refreshDocuments();
    });

    main.appendChild(cb);
    main.appendChild(text);
    item.appendChild(main);
    item.appendChild(removeBtn);
    docListEl.appendChild(item);
  });
}

document.getElementById("uploadBtn").addEventListener("click", async () => {
  const input = document.getElementById("fileInput");
  const file = input.files?.[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch("/api/documents/upload", {
    method: "POST",
    body: formData,
  });
  const data = await res.json();

  if (!res.ok) {
    addMessage("assistant", `Upload failed: ${data.detail || "Unknown error"}`);
    return;
  }

  addMessage("assistant", `Indexed ${data.name} (${data.chunks_indexed} chunks).`);
  input.value = "";
  await refreshDocuments();
});

document.getElementById("urlBtn").addEventListener("click", async () => {
  const input = document.getElementById("urlInput");
  const url = input.value.trim();
  if (!url) return;

  const res = await fetch("/api/documents/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const data = await res.json();

  if (!res.ok) {
    addMessage("assistant", `URL ingest failed: ${data.detail || "Unknown error"}`);
    return;
  }

  addMessage("assistant", `Indexed URL (${data.chunks_indexed} chunks).`);
  input.value = "";
  await refreshDocuments();
});

document.getElementById("chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const questionEl = document.getElementById("questionInput");
  const question = questionEl.value.trim();
  if (!question) return;

  addMessage("user", question);
  questionEl.value = "";

  const res = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      selected_document_ids: state.selectedIds,
      session_id: state.sessionId,
      user_id: "internal-user",
    }),
  });

  const data = await res.json();
  if (!res.ok) {
    addMessage("assistant", `Query failed: ${data.detail || "Unknown error"}`);
    return;
  }

  state.sessionId = data.session_id || state.sessionId;
  addMessage("assistant", stripModelCitations(data.answer));
  renderCitations(data.citations);
});

refreshDocuments();

window.addEventListener("focus", () => {
  refreshDocumentsWithRetry(0);
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    refreshDocumentsWithRetry(0);
  }
});
