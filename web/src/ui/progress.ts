export class ProgressController {
  private overlayEl!: HTMLElement;
  private titleEl!: HTMLElement;
  private fillEl!: HTMLElement;
  private detailEl!: HTMLElement;

  init() {
    this.overlayEl = document.getElementById("progress-overlay") as HTMLElement;
    this.titleEl = document.getElementById("progress-stage-title") as HTMLElement;
    this.fillEl = document.getElementById("progress-fill") as HTMLElement;
    this.detailEl = document.getElementById("progress-detail-text") as HTMLElement;
  }

  public show(stageName: string, progress: number, detail = "") {
    this.overlayEl.classList.remove("hidden");
    const formattedStage = stageName.charAt(0).toUpperCase() + stageName.slice(1).replace(/_/g, " ");
    this.titleEl.textContent = `${formattedStage}...`;
    const pct = Math.round(progress * 100);
    this.fillEl.style.width = `${pct}%`;
    this.detailEl.textContent = detail || `${pct}% complete`;
  }

  public setStatusText(msg: string) {
    this.overlayEl.classList.remove("hidden");
    this.detailEl.textContent = msg;
  }

  public hide() {
    this.overlayEl.classList.add("hidden");
  }
}

export const progressController = new ProgressController();
