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

    // Wheel zoom on viewer ONLY with { passive: false }
    this.viewportEl.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 0.85;
      this.zoom(factor);
    }, { passive: false });

    // Pointer pan drag attached ONLY to viewportEl
    this.viewportEl.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      this.isDragging = true;
      this.startX = e.clientX - this.panX;
      this.startY = e.clientY - this.panY;
      try {
        this.viewportEl.setPointerCapture(e.pointerId);
      } catch (_) {}
    });

    this.viewportEl.addEventListener("pointermove", (e) => {
      if (!this.isDragging) return;
      this.panX = e.clientX - this.startX;
      this.panY = e.clientY - this.startY;
      this.applyTransform();
    });

    const stopDragging = (e: PointerEvent) => {
      if (this.isDragging) {
        this.isDragging = false;
        try {
          this.viewportEl.releasePointerCapture(e.pointerId);
        } catch (_) {}
      }
    };

    this.viewportEl.addEventListener("pointerup", stopDragging);
    this.viewportEl.addEventListener("pointercancel", stopDragging);

    // Multi-touch pinch-to-zoom on viewportEl ONLY
    let initialPinchDist = 0;
    let initialPinchScale = 1.0;

    this.viewportEl.addEventListener("touchstart", (e) => {
      if (e.touches.length === 2) {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        initialPinchDist = Math.hypot(dx, dy);
        initialPinchScale = this.scale;
      }
    }, { passive: false });

    this.viewportEl.addEventListener("touchmove", (e) => {
      if (e.touches.length === 2 && initialPinchDist > 0) {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.hypot(dx, dy);
        const factor = dist / initialPinchDist;
        this.scale = Math.max(0.1, Math.min(initialPinchScale * factor, 20.0));
        this.updateZoomText();
        this.applyTransform();
      }
    }, { passive: false });

    this.viewportEl.addEventListener("touchend", (e) => {
      if (e.touches.length < 2) {
        initialPinchDist = 0;
      }
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

    // Window resize observer to refit or update boundaries
    window.addEventListener("resize", () => {
      if (this.refImageEl.complete && this.refImageEl.naturalWidth > 0) {
        this.fitToViewport();
      }
    });
  }

  public setReferenceImage(
    url: string,
    onLoadSuccess?: () => void,
    onLoadError?: (err: string) => void
  ) {
    // Attach event listeners BEFORE setting .src to prevent race conditions
    let handled = false;

    this.refImageEl.onload = () => {
      if (handled) return;
      handled = true;

      const w = this.refImageEl.naturalWidth;
      const h = this.refImageEl.naturalHeight;

      if (!w || !h || isNaN(w) || isNaN(h) || w <= 0 || h <= 0) {
        this.refImageEl.style.display = "none";
        onLoadError?.("Image decoding failed: Natural image dimensions are zero or invalid.");
        return;
      }

      this.refImageEl.style.display = "block";
      this.fitToViewport();
      onLoadSuccess?.();
    };

    this.refImageEl.onerror = () => {
      if (handled) return;
      handled = true;
      this.refImageEl.style.display = "none";
      onLoadError?.("Failed to decode image. Please check that the file is a valid PNG, JPEG, or WEBP image.");
    };

    this.refImageEl.src = url;

    // In case the image was already cached/loaded synchronously
    if (this.refImageEl.complete && this.refImageEl.naturalWidth > 0 && !handled) {
      handled = true;
      this.refImageEl.style.display = "block";
      this.fitToViewport();
      onLoadSuccess?.();
    }
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

  public updateLiveSvg(params: import("../state").PipelineParams) {
    const svgEl = this.svgHostEl?.querySelector("svg");
    if (!svgEl) return;

    // 1. Contour Lines Layer
    const contourLayer = this.svgHostEl.querySelector("#layer-90-lines-contour") as SVGElement | null;
    if (contourLayer) {
      contourLayer.style.display = params.contour_lines.enabled ? "inline" : "none";
      if (params.contour_lines.enabled) {
        // Adjust opacity based on darken factor (0.1 to 1.0)
        contourLayer.style.opacity = `${Math.min(1.0, Math.max(0.15, params.contour_lines.darken * 1.4))}`;

        // Scale stroke widths proportionally
        const paths = contourLayer.querySelectorAll<SVGPathElement>("path");
        paths.forEach((p) => {
          let base = parseFloat(p.getAttribute("data-base-width") || "");
          if (isNaN(base) || base <= 0) {
            base = parseFloat(p.getAttribute("stroke-width") || "1.5");
            p.setAttribute("data-base-width", `${base}`);
          }
          const scaleFactor = params.contour_lines.width_max / 3.0;
          p.setAttribute("stroke-width", `${Math.max(0.2, (base * scaleFactor)).toFixed(2)}`);
        });
      }
    }

    // 2. Detail Inking Layer
    const detailLayer = this.svgHostEl.querySelector("#layer-95-lines-detail") as SVGElement | null;
    if (detailLayer) {
      detailLayer.style.display = params.detail_lines.enabled ? "inline" : "none";
      if (params.detail_lines.enabled) {
        const paths = detailLayer.querySelectorAll<SVGPathElement>("path");
        paths.forEach((p) => {
          const sw = p.getAttribute("stroke-width");
          if (sw !== null) {
            let base = parseFloat(p.getAttribute("data-base-width") || "");
            if (isNaN(base) || base <= 0) {
              base = parseFloat(sw || "1.0");
              p.setAttribute("data-base-width", `${base}`);
            }
            const scaled = base * params.detail_lines.width_scale;
            p.setAttribute("stroke-width", `${Math.max(0.2, scaled).toFixed(2)}`);
          }
        });
      }
    }
  }

  public getSvgString(): string {
    const svgEl = this.svgHostEl?.querySelector("svg");
    if (!svgEl) return "";
    return new XMLSerializer().serializeToString(svgEl);
  }

  private zoom(factor: number) {
    this.scale = Math.max(0.1, Math.min(this.scale * factor, 20.0));
    this.updateZoomText();
    this.applyTransform();
  }

  public fitToViewport() {
    if (!this.viewportEl || !this.transformEl) return;
    const rect = this.viewportEl.getBoundingClientRect();
    const contentW = this.refImageEl.naturalWidth || 600;
    const contentH = this.refImageEl.naturalHeight || 400;

    // Guard against 0 / NaN dimensions
    if (!contentW || !contentH || isNaN(contentW) || isNaN(contentH) || contentW <= 0 || contentH <= 0) {
      return;
    }

    const vpW = rect.width > 0 ? rect.width : 600;
    const vpH = rect.height > 0 ? rect.height : 400;

    const scaleX = (vpW * 0.85) / contentW;
    const scaleY = (vpH * 0.85) / contentH;
    let targetScale = Math.min(scaleX, scaleY, 1.5);

    if (isNaN(targetScale) || !isFinite(targetScale) || targetScale <= 0) {
      targetScale = 1.0;
    }
    this.scale = targetScale;

    let px = (vpW - contentW * this.scale) / 2;
    let py = (vpH - contentH * this.scale) / 2;

    if (isNaN(px) || !isFinite(px)) px = 0;
    if (isNaN(py) || !isFinite(py)) py = 0;

    this.panX = Math.round(px);
    this.panY = Math.round(py);

    this.transformEl.style.width = `${contentW}px`;
    this.transformEl.style.height = `${contentH}px`;

    this.updateZoomText();
    this.applyTransform();
  }

  private updateZoomText() {
    if (this.zoomTextEl) {
      this.zoomTextEl.textContent = `${Math.round(this.scale * 100)}%`;
    }
  }

  private applyTransform() {
    if (this.transformEl) {
      this.transformEl.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale})`;
    }
  }
}

export const viewerController = new ViewerController();
