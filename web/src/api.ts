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

export async function testHealthz(url?: string): Promise<{ ok: boolean; message: string }> {
  const targetUrl = (url || appState.getApiUrl()).replace(/\/+$/, "");
  try {
    const res = await fetch(`${targetUrl}/healthz`, { method: "GET" });
    if (!res.ok) {
      return { ok: false, message: `Server responded with HTTP ${res.status}` };
    }
    const data = await res.json();
    return data.ok ? { ok: true, message: "Server connection OK!" } : { ok: false, message: "Invalid health response" };
  } catch (err: any) {
    return { ok: false, message: `Could not reach server: ${err.message}` };
  }
}

export async function submitJob(
  file: File,
  params: PipelineParams,
  onStatusUpdate?: (msg: string) => void
): Promise<string> {
  const baseUrl = appState.getApiUrl();
  const formData = new FormData();
  formData.append("file", file);
  formData.append("params", JSON.stringify(params));

  let attempts = 0;
  const maxAttempts = 15; // 90 seconds backoff for waking up Render instances

  while (attempts < maxAttempts) {
    try {
      attempts++;
      const res = await fetch(`${baseUrl}/jobs`, {
        method: "POST",
        headers: getHeaders(false),
        body: formData,
      });

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
        await new Promise((r) => setTimeout(r, 5000));
        continue;
      }
      if (!res.ok) {
        throw new Error(`Server returned error HTTP ${res.status}`);
      }

      const data = await res.json();
      return data.job_id;
    } catch (err: any) {
      if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
        if (onStatusUpdate) {
          onStatusUpdate(`Server is waking up (attempt ${attempts}/${maxAttempts}), retrying...`);
        }
        await new Promise((r) => setTimeout(r, Math.min(3000 * attempts, 10000)));
      } else {
        throw err;
      }
    }
  }

  throw new Error("Server wake-up timed out after 90 seconds. Please check your API URL.");
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
