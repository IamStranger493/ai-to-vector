
export class ViewerController {
  private scale = 1.0;
  private panX = 0;
  private panY = 0;
  private isDragging = false;
  private startX = 0;
  private startY = 0;

  private viewportEl!: HTMLElement;
  private transformEl!: HTMLElement;
  private refImageEl!: HTMLImageElement;
  private svgHostEl!: HTMLElement;
  private zoomTextEl!: HTMLElement;
  private compareSliderEl!: HTMLInputElement;

  init() {
    this.viewportEl = document.getElementById("viewport") as HTMLElement;
    this.transformEl = document.getElementById("canvas-transform") as HTMLElement;
    this.refImageEl = document.getElementById("ref-image") as HTMLImageElement;
    this.svgHostEl = document.getElementById("svg-host") as HTMLElement;
    this.zoomTextEl = document.getElementById("zoom-level-text") as HTMLElement;
    this.compareSliderEl = document.getElementById("compare-slider") as HTMLInputElement;

    this.bindEvents();
  }

  private bindEvents() {
    // Zoom buttons
    document.getElementById("btn-zoom-in")?.addEventListener("click", () => this.zoom(1.2));
    document.getElementById("btn-zoom-out")?.addEventListener("click", () => this.zoom(0.8));
    document.getElementById("btn-zoom-reset")?.addEventListener("click", () => this.fitToViewport());

    // Wheel zoom
    this.viewportEl.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 0.85;
      this.zoom(factor);
    }, { passive: false });

    // Pan drag
    this.viewportEl.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      this.isDragging = true;
      this.startX = e.clientX - this.panX;
      this.startY = e.clientY - this.panY;
    });

    window.addEventListener("mousemove", (e) => {
      if (!this.isDragging) return;
      this.panX = e.clientX - this.startX;
      this.panY = e.clientY - this.startY;
      this.applyTransform();
    });

    window.addEventListener("mouseup", () => {
      this.isDragging = false;
    });

    // Compare slider
    this.compareSliderEl.addEventListener("input", () => {
      const val = parseFloat(this.compareSliderEl.value) / 100.0;
      this.svgHostEl.style.opacity = `${val}`;
    });

    // Background switchers
    document.querySelectorAll(".bg-btn[data-bg]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".bg-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const bg = btn.getAttribute("data-bg");
        this.viewportEl.className = `viewport bg-${bg}`;
      });
    });
  }

  public setReferenceImage(url: string) {
    this.refImageEl.src = url;
    this.refImageEl.style.display = "block";
    this.refImageEl.onload = () => {
      this.fitToViewport();
    };
  }

  public setSvgContent(svgString: string) {
    this.svgHostEl.innerHTML = svgString;
    const svgEl = this.svgHostEl.querySelector("svg");
    if (svgEl) {
      svgEl.style.width = "100%";
      svgEl.style.height = "100%";
    }
    this.fitToViewport();
  }

  private zoom(factor: number) {
    this.scale = Math.max(0.1, Math.min(this.scale * factor, 20.0));
    this.updateZoomText();
    this.applyTransform();
  }

  private fitToViewport() {
    const rect = this.viewportEl.getBoundingClientRect();
    const contentW = this.refImageEl.naturalWidth || 600;
    const contentH = this.refImageEl.naturalHeight || 400;

    const scaleX = (rect.width * 0.85) / contentW;
    const scaleY = (rect.height * 0.85) / contentH;
    this.scale = Math.min(scaleX, scaleY, 1.5);

    this.panX = (rect.width - contentW * this.scale) / 2;
    this.panY = (rect.height - contentH * this.scale) / 2;

    this.transformEl.style.width = `${contentW}px`;
    this.transformEl.style.height = `${contentH}px`;

    this.updateZoomText();
    this.applyTransform();
  }

  private updateZoomText() {
    this.zoomTextEl.textContent = `${Math.round(this.scale * 100)}%`;
  }

  private applyTransform() {
    this.transformEl.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale})`;
  }
}

export const viewerController = new ViewerController();
