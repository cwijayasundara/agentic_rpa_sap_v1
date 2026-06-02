const $ = (id) => document.getElementById(id);

async function post(url, body) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

function renderRpa(res) {
  const statusEl = $("rpa-status");
  if (res.status === "COMPLETED" && res.invoice_total === 0) {
    statusEl.textContent = `⚠ COMPLETED but invoice = $0 (silently wrong)`;
    statusEl.className = "status warn";
  } else if (res.status === "COMPLETED") {
    statusEl.textContent = `✓ COMPLETED — invoice $${res.invoice_total}`;
    statusEl.className = "status ok";
  } else {
    statusEl.textContent = `✗ ESCALATED at ${res.failed_step} — human needed`;
    statusEl.className = "status fail";
  }
  const ol = $("rpa-steps");
  ol.innerHTML = "";
  for (const s of res.steps) {
    const li = document.createElement("li");
    li.className = s.ok ? "ok" : "fail";
    li.textContent = `${s.ok ? "✓" : "✗"} ${s.step} (${s.detail})`;
    ol.appendChild(li);
  }
}

function renderAgent(res) {
  $("agent-status").textContent = "✓ chain handled by agents";
  $("agent-status").className = "status ok";
  const box = $("agent-transcript");
  box.innerHTML = "";
  for (const m of res.transcript) {
    const div = document.createElement("div");
    const authorDiv = document.createElement("div");
    authorDiv.className = "author";
    authorDiv.textContent = m.author;
    const textDiv = document.createElement("div");
    textDiv.textContent = m.text;
    div.appendChild(authorDiv);
    div.appendChild(textDiv);
    box.appendChild(div);
  }
}

$("run").addEventListener("click", async () => {
  const scenario = $("scenario").value;
  $("rpa-status").textContent = "running…";
  $("agent-status").textContent = "running… (LLM, may take a few seconds)";
  $("rpa-steps").innerHTML = "";
  $("agent-transcript").innerHTML = "";
  const [rpa, agent] = await Promise.all([
    post("/api/rpa/run", { scenario }),
    post("/api/agent/run", { scenario }),
  ]);
  renderRpa(rpa);
  renderAgent(agent);
});
