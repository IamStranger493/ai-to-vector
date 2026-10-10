import { appState } from "./state";
import { submitJob, pollJob, fetchJobSvg, fetchJobPngBlob, fetchJobReport } from "./api";
import { initUpload } from "./ui/upload";
import { initParamsPanel } from "./ui/paramsPanel";
import { viewerController } from "./ui/viewer";
import { layersPanelController } from "./ui/layersPanel";
import { progressController } from "./ui/progress";
import { initSettingsDialog } from "./ui/settingsDialog";
import * as fflate from "fflate";

let activeObjectUrl: string | null = null;

function scrollViewerIntoViewOnMobile() {
  // On narrow screens the viewer sits below the long parameter list; bring it into view.
  if (window.matchMedia("(max-width: 960px)").matches) {
    document.getElementById("viewer-stage")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function showUploadError(msg: string | null) {
  const banner = document.getElementById("upload-error-banner");
  if (!banner) return;
  if (msg) {
    banner.textContent = msg;
    banner.classList.remove("hidden");
  } else {
    banner.textContent = "";
    banner.classList.add("hidden");
  }
}

function handleImageFile(file: File) {
  showUploadError(null);
  const newUrl = URL.createObjectURL(file);
  viewerController.setReferenceImage(
    newUrl,
    () => {
      // Successful decode & load: safe to revoke previous blob URL
      if (activeObjectUrl && activeObjectUrl.startsWith("blob:") && activeObjectUrl !== newUrl) {
        URL.revokeObjectURL(activeObjectUrl);
      }
      activeObjectUrl = newUrl;
      appState.currentImageUrl = newUrl;
      showUploadError(null);
      scrollViewerIntoViewOnMobile();
    },
    (err) => {
      showUploadError(err);
      try {
        URL.revokeObjectURL(newUrl);
      } catch (_) {}
    }
  );
}

document.addEventListener("DOMContentLoaded", () => {
  // The preset dropdown shows "Accurate" first, so make the real params match it
  appState.loadPreset("Accurate");
  const initialPresetSelect = document.getElementById("preset-select") as HTMLSelectElement | null;
  if (initialPresetSelect) initialPresetSelect.value = "Accurate";

  // Initialize UI subsystems
  viewerController.init();
  layersPanelController.init();
  progressController.init();
  initSettingsDialog();

  initParamsPanel(() => {
    const presetSelect = document.getElementById("preset-select") as HTMLSelectElement;
    if (presetSelect) presetSelect.value = "custom";
  });

  // Preset Selector
  const presetSelect = document.getElementById("preset-select") as HTMLSelectElement;
  presetSelect.addEventListener("change", () => {
    appState.loadPreset(presetSelect.value);
    initParamsPanel(() => {});
  });

  // Save Preset button
  document.getElementById("btn-save-preset")?.addEventListener("click", () => {
    const name = prompt("Enter a name for this custom preset:");
    if (name) {
      appState.savePreset(name);
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = `Preset: ${name}`;
      presetSelect.appendChild(opt);
      presetSelect.value = name;
      alert(`Preset '${name}' saved!`);
    }
  });

  initUpload(
    (file) => {
      handleImageFile(file);
    },
    (sampleName) => {
      loadSampleImage(sampleName);
    },
    (err) => {
      showUploadError(err);
    }
  );

  // Run Vectorize Pipeline
  const runBtn = document.getElementById("btn-run") as HTMLButtonElement;
  runBtn.addEventListener("click", async () => {
    if (!appState.currentImageFile) {
      alert("Please upload or choose a reference image first.");
      return;
    }

    try {
      runBtn.disabled = true;
      progressController.show("upload", 0.05, "Uploading image to worker pipeline...");

      const jobId = await submitJob(
        appState.currentImageFile,
        appState.params,
        (statusMsg) => progressController.setStatusText(statusMsg)
      );

      appState.currentJobId = jobId;

      // Poll status
      await pollJob(jobId, (status) => {
        progressController.show(status.stage || "processing", status.progress, `Stage: ${status.stage}`);
      });

      // Fetch results
      progressController.show("download", 0.95, "Downloading vector SVG and report...");
      const svgStr = await fetchJobSvg(jobId);
      const report = await fetchJobReport(jobId);

      appState.resultSvg = svgStr;
      appState.resultReport = report;

      // Inline SVG into DOM
      viewerController.setSvgContent(svgStr);

      // Update Layers Panel
      const svgHost = document.getElementById("svg-host") as HTMLElement;
      layersPanelController.updateFromSvg(svgHost);

      // Update Metrics Panel
      updateMetricsView(report);

      // Enable download buttons
      enableDownloads(jobId, svgStr, report);

      progressController.hide();
      scrollViewerIntoViewOnMobile();
    } catch (err: any) {
      progressController.hide();
      alert(`Vectorization failed: ${err.message}`);
    } finally {
      runBtn.disabled = false;
    }
  });
});

function updateMetricsView(report: any) {
  const container = document.getElementById("metrics-view");
  if (!container || !report) return;

  const m = report.metrics || {};
  const s = report.stats || {};
  const g = report.gaps || {};

  container.innerHTML = `
    <div class="metric-row">
      <span class="metric-label">MAE / Fidelity Error:</span>
      <span class="metric-val ${m.mae <= 8.14 ? "metric-pass" : "metric-warn"}">${m.mae}</span>
    </div>
    <div class="metric-row">
      <span class="metric-label">PSNR:</span>
      <span class="metric-val ${m.psnr >= 25.5 ? "metric-pass" : "metric-warn"}">${m.psnr} dB</span>
    </div>
    <div class="metric-row">
      <span class="metric-label">SSIM:</span>
      <span class="metric-val metric-pass">${m.ssim}</span>
    </div>
    <div class="metric-row">
      <span class="metric-label">Gap Pixels (0.5x, 1x, 2x):</span>
      <span class="metric-val ${g.total === 0 ? "metric-pass" : "metric-warn"}">
        ${g.counts ? `${g.counts["0.5x"]} / ${g.counts["1.0x"]} / ${g.counts["2.0x"]}` : "0"}
      </span>
    </div>
    <div class="metric-row">
      <span class="metric-label">Path Count / Nodes:</span>
      <span class="metric-val">${s.paths} paths / ${s.nodes} nodes</span>
    </div>
    <div class="metric-row">
      <span class="metric-label">SVG File Size:</span>
      <span class="metric-val">${s.size_mb || 0} MB (${Math.round((s.size_bytes || 0) / 1024)} KB)</span>
    </div>
  `;
}

function enableDownloads(jobId: string, svgStr: string, report: any) {
  const btnSvg = document.getElementById("btn-dl-svg") as HTMLButtonElement;
  const btnPng = document.getElementById("btn-dl-png") as HTMLButtonElement;
  const btnZip = document.getElementById("btn-dl-zip") as HTMLButtonElement;
  const btnRep = document.getElementById("btn-dl-report") as HTMLButtonElement;

  btnSvg.disabled = false;
  btnPng.disabled = false;
  btnZip.disabled = false;
  btnRep.disabled = false;

  btnSvg.onclick = () => downloadFile("vector_illustration.svg", svgStr, "image/svg+xml");
  btnRep.onclick = () => downloadFile("report.json", JSON.stringify(report, null, 2), "application/json");

  btnPng.onclick = async () => {
    const blob = await fetchJobPngBlob(jobId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "vector_preview.png";
    a.click();
    URL.revokeObjectURL(url);
  };

  btnZip.onclick = () => exportLayersZip(svgStr);
}

function exportLayersZip(svgStr: string) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgStr, "image/svg+xml");
  const svgRoot = doc.querySelector("svg");
  if (!svgRoot) return;

  const viewBox = svgRoot.getAttribute("viewBox") || "0 0 1000 1000";
  const layers = doc.querySelectorAll("svg > g[id^='layer-']");

  const files: Record<string, Uint8Array> = {};

  layers.forEach((layer) => {
    const id = layer.getAttribute("id") || "layer";
    const layerSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}">${layer.outerHTML}</svg>`;
    files[`${id}.svg`] = fflate.strToU8(layerSvg);
  });

  fflate.zip(files, (err, data) => {
    if (err) {
      alert("Failed to create ZIP: " + err);
      return;
    }
    const blob = new Blob([data.buffer as ArrayBuffer], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "vector_layers.zip";
    a.click();
    URL.revokeObjectURL(url);
  });
}

function downloadFile(name: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function loadSampleImage(sampleName: string) {
  // Synthesize sample canvas directly client-side for immediate offline responsiveness
  const canvas = document.createElement("canvas");
  canvas.width = 400;
  canvas.height = 300;
  const ctx = canvas.getContext("2d")!;

  if (sampleName === "illustration") {
    ctx.fillStyle = "#f0f4f8";
    ctx.fillRect(0, 0, 400, 300);
    ctx.fillStyle = "#ffb432";
    ctx.beginPath();
    ctx.arc(300, 80, 40, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#465a8c";
    ctx.beginPath();
    ctx.moveTo(0, 220); ctx.lineTo(120, 90); ctx.lineTo(250, 220);
    ctx.fill();
    ctx.fillStyle = "#3ca069";
    ctx.beginPath();
    ctx.arc(100, 280, 100, 0, Math.PI * 2);
    ctx.fill();
  } else if (sampleName === "desert") {
    const grad = ctx.createLinearGradient(0, 0, 0, 180);
    grad.addColorStop(0, "#78aae6");
    grad.addColorStop(1, "#f5c896");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 400, 180);
    ctx.fillStyle = "#e6a555";
    ctx.fillRect(0, 180, 400, 120);
    ctx.fillStyle = "#1e50b4";
    ctx.beginPath();
    ctx.arc(160, 160, 30, 0, Math.PI * 2);
    ctx.fill();
  } else {
    ctx.fillStyle = "#d2e1eb";
    ctx.fillRect(0, 0, 400, 300);
    ctx.fillStyle = "#d7c8b4";
    ctx.fillRect(50, 120, 120, 120);
    ctx.fillStyle = "#b45a46";
    ctx.beginPath();
    ctx.moveTo(40, 120); ctx.lineTo(110, 70); ctx.lineTo(180, 120);
    ctx.fill();
    ctx.fillStyle = "#dc3c3c";
    ctx.fillRect(220, 200, 30, 60);
  }

  canvas.toBlob((blob) => {
    if (blob) {
      const file = new File([blob], `${sampleName}.png`, { type: "image/png" });
      appState.currentImageFile = file;
      handleImageFile(file);
    }
  });
}
