/* ═══════════════════════════════════════════════════
   AI Video Studio — Frontend Logic
   Handles: prompt submission, job polling, UI transitions,
            video playback, download
═══════════════════════════════════════════════════ */

// ─── State ───
let currentJobId = null;
let pollInterval = null;
let currentVideoUrl = null;
let isGif = false;

// ─── Step progress map ───
const StepMap = {
    starting: { active: 0, pct: 5, subtitle: "Starting pipeline…" },
    enhancing: { active: 1, pct: 15, subtitle: "Gemini Flash is enhancing your prompt…" },
    enhanced: { active: 1, pct: 30, subtitle: "Prompt enhanced! Generating images…" },
    generating_images: { active: 2, pct: 40, subtitle: "Imagen 4 is creating 4 unique scenes…" },
    images_done: { active: 2, pct: 65, subtitle: "Images ready! Starting video generation…" },
    creating_video: { active: 3, pct: 75, subtitle: "Veo 2 is bringing your visuals to life…" },
    done: { active: 3, pct: 100, subtitle: "Your video is ready!" },
    error: { active: 0, pct: 0, subtitle: "Something went wrong." }
};

// ─── Dom Refs ───
const screens = {
    input: document.getElementById("screen-input"),
    loading: document.getElementById("screen-loading"),
    result: document.getElementById("screen-result")
};

// ─── Char counter ───
const promptEl = document.getElementById("prompt");
const charCountEl = document.getElementById("char-count");
promptEl.addEventListener("input", () => {
    charCountEl.textContent = promptEl.value.length;
});

// ─── Example prompt setter ───
function setExample(text) {
    promptEl.value = text;
    charCountEl.textContent = text.length;
    promptEl.focus();
}

// ─── Show / hide screen ───
function showScreen(name) {
    Object.entries(screens).forEach(([key, el]) => {
        el.classList.remove("active");
        el.style.display = "none";
    });
    const target = screens[name];
    target.style.display = "flex";
    requestAnimationFrame(() => target.classList.add("active"));
}

// ═══════════════════════════════════════════════════
//  START GENERATION
// ═══════════════════════════════════════════════════
async function startGeneration() {
    const prompt = promptEl.value.trim();
    if (!prompt) {
        promptEl.focus();
        promptEl.style.borderColor = "#ff5acd";
        setTimeout(() => { promptEl.style.borderColor = ""; }, 1500);
        return;
    }

    // Disable button
    const btn = document.getElementById("btn-generate");
    btn.disabled = true;

    // Reset loading UI
    resetLoadingUI();
    showScreen("loading");

    try {
        const resp = await fetch("/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt })
        });
        if (!resp.ok) throw new Error("Server error: " + resp.status);
        const { jobId } = await resp.json();
        currentJobId = jobId;
        startPolling();
    } catch (err) {
        showError("Failed to start generation: " + err.message);
        btn.disabled = false;
    }
}

// ═══════════════════════════════════════════════════
//  POLLING
// ═══════════════════════════════════════════════════
function startPolling() {
    pollInterval = setInterval(pollStatus, 3000);
    pollStatus(); // immediate first check
}

function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
}

async function pollStatus() {
    if (!currentJobId) return;
    try {
        const resp = await fetch(`/status/${currentJobId}`);
        if (!resp.ok) return;
        const job = await resp.json();
        applyJobUpdate(job);
    } catch (e) {
        console.warn("Poll error:", e);
    }
}

// ─── Apply job update to UI ───
function applyJobUpdate(job) {
    const map = StepMap[job.step] || StepMap.starting;

    // Subtitle
    document.getElementById("loading-subtitle").textContent = map.subtitle;

    // Progress bar
    document.getElementById("loading-fill").style.width = map.pct + "%";

    // Steps
    updateSteps(map.active, job.step === "done");

    // Enhanced prompt preview
    if (job.enhancedPrompt) {
        showEnhancedPrompt(job.enhancedPrompt);
    }

    // Image strip preview
    if (job.images && job.images.length > 0) {
        showImageStrip(job.images);
    }

    // Terminal states
    if (job.status === "done") {
        stopPolling();
        setTimeout(() => showResult(job), 600);
    } else if (job.status === "error") {
        stopPolling();
        showError(job.error || "Unknown error");
    }
}

function updateSteps(activeStep, allDone) {
    [1, 2, 3].forEach(n => {
        const el = document.getElementById(`step-${n}`);
        el.classList.remove("active", "done");
        if (n < activeStep || allDone) el.classList.add("done");
        else if (n === activeStep) el.classList.add("active");
    });
}

function showEnhancedPrompt(text) {
    const box = document.getElementById("enhanced-prompt-box");
    const txt = document.getElementById("enhanced-prompt-text");
    txt.textContent = text;
    box.style.display = "block";
}

function showImageStrip(images) {
    const strip = document.getElementById("image-strip-preview");
    const thumbs = document.getElementById("image-thumbs");
    if (thumbs.children.length === images.length) return; // already shown
    thumbs.innerHTML = "";
    images.forEach((src, i) => {
        const img = document.createElement("img");
        img.src = src;
        img.alt = `Generated scene ${i + 1}`;
        img.style.animationDelay = `${i * 0.12}s`;
        thumbs.appendChild(img);
    });
    strip.style.display = "block";
}

// ═══════════════════════════════════════════════════
//  SHOW RESULT
// ═══════════════════════════════════════════════════
function showResult(job) {
    currentVideoUrl = job.videoUrl;
    isGif = job.videoUrl && job.videoUrl.endsWith(".gif");

    const videoContainer = document.getElementById("video-container");

    if (isGif) {
        // Replace video element with img for GIF playback
        videoContainer.innerHTML = `
      <div class="gif-container">
        <img src="${job.videoUrl}" alt="Generated video animation" />
      </div>`;
    } else {
        const videoPlayer = document.getElementById("video-player");
        if (videoPlayer) {
            videoPlayer.src = job.videoUrl;
            videoPlayer.load();
            videoPlayer.play().catch(() => { });
        }
    }

    // Enhanced prompt
    const rptText = document.getElementById("result-prompt-text");
    if (rptText && job.enhancedPrompt) {
        rptText.textContent = job.enhancedPrompt;
        document.getElementById("result-prompt-box").style.display = "block";
    }

    // Image grid
    const grid = document.getElementById("result-images-grid");
    if (grid && job.images) {
        grid.innerHTML = "";
        job.images.forEach((src, i) => {
            const img = document.createElement("img");
            img.src = src;
            img.alt = `Scene ${i + 1}`;
            img.title = `Scene ${i + 1}`;
            img.onclick = () => openImageFullscreen(src);
            grid.appendChild(img);
        });
    }

    showScreen("result");
}

// ═══════════════════════════════════════════════════
//  VIDEO CONTROLS
// ═══════════════════════════════════════════════════
function togglePlay() {
    const video = document.getElementById("video-player");
    if (!video) return;
    if (video.paused) { video.play(); } else { video.pause(); }
}

async function downloadVideo() {
    if (!currentVideoUrl) return;

    // Extract filename from URL
    const fileName = currentVideoUrl.split("/").pop();
    const downloadUrl = `/download/${fileName}`;

    try {
        const resp = await fetch(downloadUrl);
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `ai-video-${currentJobId}.${isGif ? "gif" : "mp4"}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        // Fallback: direct link
        const a = document.createElement("a");
        a.href = currentVideoUrl;
        a.download = `ai-video.${isGif ? "gif" : "mp4"}`;
        a.click();
    }
}

// ═══════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════
function resetToStart() {
    stopPolling();
    currentJobId = null;
    currentVideoUrl = null;
    isGif = false;
    document.getElementById("btn-generate").disabled = false;
    promptEl.value = "";
    charCountEl.textContent = "0";
    showScreen("input");
}

function resetLoadingUI() {
    document.getElementById("loading-subtitle").textContent = "Initializing pipeline…";
    document.getElementById("loading-fill").style.width = "0%";
    document.getElementById("enhanced-prompt-box").style.display = "none";
    document.getElementById("image-strip-preview").style.display = "none";
    document.getElementById("image-thumbs").innerHTML = "";
    [1, 2, 3].forEach(n => {
        const el = document.getElementById(`step-${n}`);
        el.classList.remove("active", "done");
    });
}

function showError(msg) {
    stopPolling();
    // Sanitize error message to remove any potential API keys or sensitive URLs
    let safeMsg = msg;
    if (msg) {
        safeMsg = msg.replace(/key=[A-Za-z0-9_-]+/gi, 'key=***');
        safeMsg = safeMsg.replace(/https:\/\/[^\s]+key=[^\s]+/gi, 'https://***');
    }
    
    document.getElementById("loading-subtitle").textContent = "❌ " + safeMsg;
    document.getElementById("loading-fill").style.width = "0%";
    [1, 2, 3].forEach(n => document.getElementById(`step-${n}`).classList.remove("active", "done"));
    const btn = document.getElementById("btn-generate");
    if (btn) btn.disabled = false;

    // Show "Try again" after 2s
    setTimeout(() => {
        if (confirm("Something went wrong: " + safeMsg + "\n\nReturn to start?")) {
            resetToStart();
        }
    }, 500);
}

function openImageFullscreen(src) {
    const overlay = document.createElement("div");
    overlay.style.cssText = `
    position:fixed;inset:0;background:rgba(0,0,0,0.92);
    z-index:9999;display:flex;align-items:center;justify-content:center;
    cursor:zoom-out;animation:fadeSlideUp 0.3s ease both;
  `;
    const img = document.createElement("img");
    img.src = src;
    img.style.cssText = `max-width:90vw;max-height:90vh;border-radius:12px;box-shadow:0 20px 80px rgba(0,0,0,0.8);`;
    overlay.appendChild(img);
    overlay.onclick = () => overlay.remove();
    document.body.appendChild(overlay);
}

// ─── Initial screen ───
showScreen("input");
