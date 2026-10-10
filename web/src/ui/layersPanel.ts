export class LayersPanelController {
  private containerEl!: HTMLElement;
  private layers: { id: string; label: string; element: SVGGElement; visible: boolean }[] = [];

  init() {
    this.containerEl = document.getElementById("layers-list") as HTMLElement;
    document.getElementById("btn-show-all-layers")?.addEventListener("click", () => {
      this.showAll();
    });
  }

  public updateFromSvg(svgContainer: HTMLElement) {
    const groupElements = svgContainer.querySelectorAll<SVGGElement>("svg > g[id^='layer-']");
    this.layers = [];

    groupElements.forEach((g) => {
      const id = g.getAttribute("id") || "";
      const label = g.getAttribute("inkscape:label") || id.replace(/^layer-/, "");
      this.layers.push({
        id,
        label,
        element: g,
        visible: g.style.display !== "none",
      });
    });

    this.render();
  }

  private render() {
    if (this.layers.length === 0) {
      this.containerEl.innerHTML = '<p class="empty-hint">No layers found in current vector.</p>';
      return;
    }

    this.containerEl.innerHTML = "";

    // Render from top to bottom (reversed array)
    const reversed = [...this.layers].reverse();

    reversed.forEach((layer) => {
      const item = document.createElement("div");
      item.className = "layer-item";

      const nameSpan = document.createElement("span");
      nameSpan.className = "layer-name";
      nameSpan.textContent = layer.label;

      const controls = document.createElement("div");
      controls.className = "layer-controls";

      // Solo button
      const soloBtn = document.createElement("button");
      soloBtn.className = "layer-btn";
      soloBtn.textContent = "Solo";
      soloBtn.title = `Solo layer ${layer.label}`;
      soloBtn.addEventListener("click", () => this.solo(layer.id));

      // Visibility Toggle button
      const visBtn = document.createElement("button");
      visBtn.className = `layer-btn ${layer.visible ? "active" : ""}`;
      visBtn.textContent = layer.visible ? "👁" : "🚫";
      visBtn.title = layer.visible ? "Hide layer" : "Show layer";
      visBtn.addEventListener("click", () => this.toggle(layer.id, visBtn));

      controls.appendChild(soloBtn);
      controls.appendChild(visBtn);

      item.appendChild(nameSpan);
      item.appendChild(controls);
      this.containerEl.appendChild(item);
    });
  }

  private toggle(layerId: string, button: HTMLButtonElement) {
    const layer = this.layers.find((l) => l.id === layerId);
    if (!layer) return;

    layer.visible = !layer.visible;
    layer.element.style.display = layer.visible ? "" : "none";
    button.textContent = layer.visible ? "👁" : "🚫";
    button.classList.toggle("active", layer.visible);
  }

  private solo(layerId: string) {
    this.layers.forEach((layer) => {
      layer.visible = (layer.id === layerId);
      layer.element.style.display = layer.visible ? "" : "none";
    });
    this.render();
  }

  private showAll() {
    this.layers.forEach((layer) => {
      layer.visible = true;
      layer.element.style.display = "";
    });
    this.render();
  }
}

export const layersPanelController = new LayersPanelController();
