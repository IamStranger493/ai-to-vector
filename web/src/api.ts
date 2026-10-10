import { appState } from "./state";
import type { PipelineParams } from "./state";

export interface JobStatusResponse {
  id: string;
  status: "queued" | "running" | "done" | "error";
  stage?: string;
  progress: number;
  queue_position: number;
  error?: string | null;
  created_at: string;
  warnings?: string[];
}

function getHeaders(_includeContentType = true): HeadersInit {
  const headers: Record<string, string> = {};
  const key = appState.getApiKey();
  if (key) {
    headers["X-API-Key"] = key;
  }
  return headers;
}

type Diagnosis = "ok" | "cors" | "unreachable";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * ok          = /healthz answered and the browser may read it (server up, CORS fine)
 * cors        = something answered, but the browser blocked it (missing CORS header). Also what a waking
 *               Render instance looks like for a moment, so callers keep polling before blaming CORS.
 * unreachable = nothing answered (wrong URL, server down or still booting)
 */
async function probe(baseUrl: string): Promise<Diagnosis> {
  try {
    const res = await fetch(`${baseUrl}/healthz?_=${Date.now()}`, { method: "GET" });
    return res.ok ? "ok" : "unreachable";
  } catch {
    try {
      await fetch(`${baseUrl}/healthz?_=${Date.now()}`, { method: "GET", mode: "no-cors" });
      return "cors";
    } catch {
      return "unreachable";
    }
  }
}

function isLocalUrl(url: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/i.test(url);
}

function corsMessage(): string {
  return (
    `The server answers but blocks this site (CORS). On Render set ALLOWED_ORIGINS=${location.origin} ` +
    `(exact, no trailing slash) and redeploy. If the service was just waking up, try again in a minute.`
  );
}

function unreachableMessage(baseUrl: string, seconds: number): string {
  if (isLocalUrl(baseUrl)) {
    return (
      `Cannot reach the API at ${baseUrl}. If your backend is running on Render, click Settings (⚙️) at the top right ` +
      `and paste your Render URL (e.g. https://vectorizer-api.onrender.com).`
    );
  }
  return (
    `Cannot reach the API at ${baseUrl} after ${seconds}s. Check the API URL in Settings and ensure the Render ` +
    `service is running (open ${baseUrl}/healthz in a new tab, it should show {"ok":true}). Render free tier instances take ~1 minute to spin up.`
  );
}

export async function testHealthz(url?: string): Promise<{ ok: boolean; message: string }> {
  const targetUrl = (url || appState.getApiUrl()).replace(/\/+$/, "");
  const d = await probe(targetUrl);
  if (d === "ok") return { ok: true, message: "Server connection OK!" };
  if (d === "cors") return { ok: false, message: corsMessage() };
  return { ok: false, message: unreachableMessage(targetUrl, 0) };
}

/** Wait until the API answers. Render free instances need about a minute to wake up. */
async function waitForServer(baseUrl: string, onStatusUpdate?: (msg: string) => void): Promise<void> {
  // API_WAKE_MAX_MS is a debug override (localStorage) used by tests.
  // Localhost fails fast (5s) because local servers don't take 2 minutes to spin up.
  const maxWaitMs = isLocalUrl(baseUrl) ? 5000 : (Number(localStorage.getItem("API_WAKE_MAX_MS")) || 150000);
  const pageIsLocal = ["localhost", "127.0.0.1"].includes(location.hostname);
  const started = Date.now();
  let last: Diagnosis = "unreachable";

  while (true) {
    last = await probe(baseUrl);
    if (last === "ok") return;

    if (isLocalUrl(baseUrl) && !pageIsLocal) {
      throw new Error(
        `The API URL is set to ${baseUrl}, which is a localhost address, but this site is running online. ` +
          `Open Settings and paste your Render URL (https://<name>.onrender.com).`
      );
    }

    const elapsed = Date.now() - started;
    if (elapsed >= maxWaitMs) break;
    if (onStatusUpdate) onStatusUpdate(`Waiting for the server to answer (${Math.round(elapsed / 1000)}s)...`);
    await sleep(3000);
  }

  if (last === "cors") throw new Error(corsMessage());
  throw new Error(unreachableMessage(baseUrl, Math.round(maxWaitMs / 1000)));
}

export async function submitJob(
  file: File,
  params: PipelineParams,
  onStatusUpdate?: (msg: string) => void
): Promise<string> {
  const baseUrl = appState.getApiUrl();

  // 1. Make sure the API is awake and reachable BEFORE uploading the image (a few bytes per check)
  await waitForServer(baseUrl, onStatusUpdate);

  // 2. Upload once. Only a full queue (429) is retried.
  const formData = new FormData();
  formData.append("file", file);
  formData.append("params", JSON.stringify(params));

  for (let attempt = 1; attempt <= 24; attempt++) {
    let res: Response;
    try {
      res = await fetch(`${baseUrl}/jobs`, { method: "POST", headers: getHeaders(false), body: formData });
    } catch (err: any) {
      throw new Error(`Upload failed, the connection to the server was lost (${err?.message || "network error"}).`);
    }

    if (res.status === 401) {
      throw new Error("Authentication failed: Missing or invalid API Key. Please configure it in Settings.");
    }
    if (res.status === 413) {
      throw new Error("Upload too large: Image exceeds maximum allowed size of 12 MB.");
    }
    if (res.status === 415) {
      throw new Error("Unsupported image format: Only PNG, JPEG, and WEBP images are supported.");
    }
    if (res.status === 422) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(`Invalid parameters: ${JSON.stringify(errJson.detail || errJson)}`);
    }
    if (res.status === 429) {
      if (onStatusUpdate) onStatusUpdate("Server queue is full. Retrying in 5 seconds...");
      await sleep(5000);
      continue;
    }
    if (!res.ok) {
      throw new Error(`Server returned error HTTP ${res.status}`);
    }

    const data = await res.json();
    return data.job_id;
  }

  throw new Error("The server queue stayed full for 2 minutes. Try again later.");
}

export async function pollJob(
  jobId: string,
  onProgress: (status: JobStatusResponse) => void
): Promise<JobStatusResponse> {
  const baseUrl = appState.getApiUrl();

  while (true) {
    const res = await fetch(`${baseUrl}/jobs/${jobId}`, {
      headers: getHeaders(),
    });

    if (res.status === 401) {
      throw new Error("Authentication failed: Check API Key in Settings.");
    }
    if (!res.ok) {
      throw new Error(`Failed to check job status: HTTP ${res.status}`);
    }

    const data: JobStatusResponse = await res.json();
    onProgress(data);

    if (data.status === "done") {
      return data;
    }
    if (data.status === "error") {
      throw new Error(data.error || "Job processing failed in worker pipeline.");
    }

    await new Promise((r) => setTimeout(r, 1500));
  }
}

export async function fetchJobSvg(jobId: string): Promise<string> {
  const res = await fetch(`${appState.getApiUrl()}/jobs/${jobId}/svg`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Could not download SVG");
  return await res.text();
}

export async function fetchJobPngBlob(jobId: string): Promise<Blob> {
  const res = await fetch(`${appState.getApiUrl()}/jobs/${jobId}/png`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Could not download PNG preview");
  return await res.blob();
}

export async function fetchJobReport(jobId: string): Promise<any> {
  const res = await fetch(`${appState.getApiUrl()}/jobs/${jobId}/report`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Could not download QA report");
  return await res.json();
}

export async function deleteJob(jobId: string): Promise<void> {
  await fetch(`${appState.getApiUrl()}/jobs/${jobId}`, {
    method: "DELETE",
    headers: getHeaders(),
  }).catch(() => {});
}
