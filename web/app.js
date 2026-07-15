const $ = (id) => document.getElementById(id);
let lastTurnId = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json"},
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function bytes(value) {
  if (value === undefined || value === null) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let n = Number(value), i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(i >= 2 ? 1 : 0)} ${units[i]}`;
}

function capability(id, enabled) {
  const el = $(id);
  el.textContent = enabled ? "Ready" : "Unavailable";
  el.className = enabled ? "ok" : "bad";
}

function renderResult(prefix, result) {
  const ok = result && result.ok;
  $(`${prefix}Ok`).textContent = result ? (ok ? "OK" : "ERROR") : "—";
  $(`${prefix}Ok`).className = `badge ${result ? (ok ? "ok" : "bad") : ""}`;
  $(`${prefix}Transcript`).textContent = result?.transcript || "—";
  $(`${prefix}Tool`).textContent = result?.plan?.tool || "—";
  const confidence = result?.plan?.confidence;
  $(`${prefix}Confidence`).textContent = confidence === undefined ? "—" : Number(confidence).toFixed(2);
  $(`${prefix}Answer`).textContent = result?.answer || "—";
  $(`${prefix}Latency`).textContent = result?.total_latency_ms === undefined ? "—" : `${result.total_latency_ms} ms`;
  $(`${prefix}Error`).textContent = result?.error || "—";
  $(`${prefix}ToolResult`).textContent = result?.tool_result ? JSON.stringify(result.tool_result, null, 2) : "—";
}

function renderTurn(turn) {
  if (!turn) return;
  lastTurnId = turn.id;
  $("turnMeta").textContent = `${turn.id} · ${turn.mode} · ${turn.audio?.duration_seconds ?? "—"} 秒`;
  $("audioPlayer").src = turn.audio_url || "";
  renderResult("local", turn.local);
  renderResult("gemini", turn.gemini);
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    $("stateText").textContent = s.message || s.state;
    $("statePill").textContent = `${s.mode.toUpperCase()} · ${s.state}`;
    $("modeSelect").value = s.mode;
    $("micLevel").style.width = `${Math.round((s.audio_level || 0) * 100)}%`;
    const gpu = s.metrics?.gpu || {};
    $("memoryText").textContent = gpu.ram_used_mb ? `${gpu.ram_used_mb} / ${gpu.ram_total_mb} MB` : (s.metrics?.memory ? `${bytes(s.metrics.memory.used_bytes)} / ${bytes(s.metrics.memory.total_bytes)}` : "—");
    $("gpuText").textContent = gpu.gpu_usage_percent !== undefined ? `${gpu.gpu_usage_percent}%` : "—";
    $("tempText").textContent = s.metrics?.temperature_c === null ? "—" : `${s.metrics?.temperature_c ?? "—"} °C`;
    $("swapText").textContent = gpu.swap_used_mb !== undefined ? `${gpu.swap_used_mb} / ${gpu.swap_total_mb} MB` : "—";
    $("loadText").textContent = s.metrics?.load_1m ?? "—";
    capability("whisperCap", s.capabilities?.whisper);
    capability("llmCap", s.capabilities?.local_llm);
    capability("geminiCap", s.capabilities?.gemini);
    $("browserRecBtn").disabled = Boolean(s.busy);
    if (s.last_turn && s.last_turn.id !== lastTurnId) {
      renderTurn(s.last_turn);
      refreshHistory();
    }
  } catch (error) {
    $("stateText").textContent = error.message;
  }
}

async function refreshHistory() {
  try {
    const data = await api("/api/history?limit=30");
    const body = $("historyBody");
    body.innerHTML = "";
    for (const item of data.items) {
      const turn = item.payload || {};
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${item.id}</td>
        <td>${item.mode}</td>
        <td>${turn.local?.transcript || turn.local?.error || "—"}</td>
        <td>${turn.gemini?.transcript || turn.gemini?.error || "—"}</td>
        <td>${turn.local?.total_latency_ms ?? "—"}</td>
        <td>${turn.gemini?.total_latency_ms ?? "—"}</td>`;
      row.addEventListener("click", () => renderTurn(turn));
      body.appendChild(row);
    }
  } catch (error) {
    console.error(error);
  }
}

// Jetson mic recording removed - using browser mic only

// Browser microphone recording
let browserStream = null;
let browserRecorder = null;
let browserChunks = [];

function encodeWav(audioBuffer) {
  const numChannels = 1;
  const sampleRate = 16000;
  const source = audioBuffer.getChannelData(0);
  // Resample if needed
  const ratio = audioBuffer.sampleRate / sampleRate;
  const newLen = Math.round(source.length / ratio);
  const samples = new Int16Array(newLen);
  for (let i = 0; i < newLen; i++) {
    const srcIdx = Math.min(Math.round(i * ratio), source.length - 1);
    const s = Math.max(-1, Math.min(1, source[srcIdx]));
    samples[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)); };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * 2, true);
  view.setUint16(32, numChannels * 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) view.setInt16(44 + i * 2, samples[i], true);
  return new Blob([buffer], {type: "audio/wav"});
}

$("browserRecBtn").addEventListener("click", async () => {
  const btn = $("browserRecBtn");
  if (browserRecorder && browserRecorder.state === "recording") {
    browserRecorder.stop();
    btn.textContent = "瀏覽器麥克風錄音";
    btn.classList.remove("recording");
    return;
  }
  try {
    browserStream = await navigator.mediaDevices.getUserMedia({audio: {sampleRate: 16000, channelCount: 1}});
    browserChunks = [];
    browserRecorder = new MediaRecorder(browserStream);
    browserRecorder.ondataavailable = (e) => { if (e.data.size > 0) browserChunks.push(e.data); };
    browserRecorder.onstop = async () => {
      browserStream.getTracks().forEach(t => t.stop());
      btn.textContent = "上傳處理中...";
      btn.disabled = true;
      try {
        const blob = new Blob(browserChunks, {type: browserRecorder.mimeType});
        const arrayBuf = await blob.arrayBuffer();
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const decoded = await audioCtx.decodeAudioData(arrayBuf);
        const wavBlob = encodeWav(decoded);
        audioCtx.close();
        const form = new FormData();
        form.append("audio", wavBlob, "recording.wav");
        await fetch("/api/upload_audio", {method: "POST", body: form});
      } catch (err) {
        alert("上傳失敗: " + err.message);
      } finally {
        btn.textContent = "瀏覽器麥克風錄音";
        btn.disabled = false;
      }
    };
    browserRecorder.start();
    btn.textContent = "停止錄音";
    btn.classList.add("recording");
  } catch (err) {
    alert("無法存取麥克風: " + err.message);
  }
});

// Jetson listen buttons removed - using browser mic only
$("modeSelect").addEventListener("change", async (event) => {
  try { await api("/api/mode", {method: "POST", body: JSON.stringify({mode: event.target.value})}); }
  catch (error) { alert(error.message); await refreshStatus(); }
});
$("refreshBtn").addEventListener("click", refreshHistory);

refreshStatus();
refreshHistory();
setInterval(refreshStatus, 700);
