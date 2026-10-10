import { appState } from "../state";

export function initUpload(
  onImageSelected: (file: File) => void,
  onSampleSelected: (sampleName: string) => void,
  onError?: (err: string) => void
) {
  const dropZone = document.getElementById("drop-zone") as HTMLElement;
  const fileInput = document.getElementById("file-input") as HTMLInputElement;

  if (dropZone && fileInput) {
    dropZone.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", (e) => {
      const files = (e.target as HTMLInputElement).files;
      if (files && files[0]) {
        validateAndSelect(files[0]);
      }
    });

    // Drag & drop
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      const files = e.dataTransfer?.files;
      if (files && files[0]) {
        validateAndSelect(files[0]);
      }
    });
  }

  // Clipboard paste support
  window.addEventListener("paste", (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith("image/")) {
        const file = items[i].getAsFile();
        if (file) {
          validateAndSelect(file);
          break;
        }
      }
    }
  });

  // Sample image chips
  document.querySelectorAll(".chip[data-sample]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const sample = chip.getAttribute("data-sample")!;
      onSampleSelected(sample);
    });
  });

  function validateAndSelect(file: File) {
    const validTypes = ["image/png", "image/jpeg", "image/webp"];
    // Some browsers or files have case variations or empty mime type
    const isImageExt = /\.(png|jpe?g|webp)$/i.test(file.name);
    if (!validTypes.includes(file.type.toLowerCase()) && !isImageExt) {
      const msg = "Unsupported image type. Please select a PNG, JPEG, or WEBP image.";
      if (onError) onError(msg);
      else alert(msg);
      return;
    }

    const maxBytes = 12 * 1024 * 1024; // 12 MB
    if (file.size > maxBytes) {
      const msg = "File too large. Maximum allowed size is 12 MB.";
      if (onError) onError(msg);
      else alert(msg);
      return;
    }

    appState.currentImageFile = file;
    onImageSelected(file);
  }
}
