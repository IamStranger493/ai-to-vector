import { appState } from "../state";
import { testHealthz } from "../api";

export function initSettingsDialog() {
  const dialog = document.getElementById("settings-dialog") as HTMLElement;
  const btnSettings = document.getElementById("btn-settings") as HTMLButtonElement;
  const btnClose = document.getElementById("btn-close-settings") as HTMLButtonElement;
  const btnSave = document.getElementById("btn-save-settings") as HTMLButtonElement;
  const btnTest = document.getElementById("btn-test-connection") as HTMLButtonElement;

  const inputUrl = document.getElementById("input-api-url") as HTMLInputElement;
  const inputKey = document.getElementById("input-api-key") as HTMLInputElement;
  const statusMsg = document.getElementById("settings-test-status") as HTMLElement;

  btnSettings.addEventListener("click", () => {
    inputUrl.value = appState.getApiUrl();
    inputKey.value = appState.getApiKey();
    statusMsg.classList.add("hidden");
    dialog.classList.remove("hidden");
  });

  const closeDialog = () => dialog.classList.add("hidden");
  btnClose.addEventListener("click", closeDialog);

  btnTest.addEventListener("click", async () => {
    statusMsg.classList.remove("hidden");
    statusMsg.textContent = "Connecting to backend health endpoint...";
    statusMsg.style.color = "var(--text-muted)";

    const res = await testHealthz(inputUrl.value);
    statusMsg.textContent = res.message;
    statusMsg.style.color = res.ok ? "var(--accent-emerald)" : "var(--accent-rose)";
  });

  btnSave.addEventListener("click", () => {
    appState.setApiUrl(inputUrl.value);
    appState.setApiKey(inputKey.value);
    closeDialog();
  });
}
