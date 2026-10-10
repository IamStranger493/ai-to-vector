export interface PipelineParams {
  working_max_side: number;
  denoise: {
    enabled: boolean;
    method: "meanshift" | "bilateral";
    sp: number;
    sr: number;
  };
  palette: {
    k: number;
    chroma_weight: number;
    sample_size: number;
    user_palette: string[] | null;
  };
  regions: {
    min_area_px: number;
    merge_delta_e: number;
    protect_delta_e: number;
    protect_max_area_px: number;
  };
  curves: {
    smooth_sigma_px: number;
    rdp_epsilon_px: number;
    fit_tolerance_px: number;
    corner_angle_deg: number;
    mode: "bezier" | "polygon";
    decimals: number;
  };
  layers: {
    grouping: "hue_tone" | "segments";
    tone_bands: number;
  };
  contour_lines: {
    enabled: boolean;
    min_delta_e: number;
    width_min: number;
    width_max: number;
    color_mode: "darker_neighbor" | "ink";
    darken: number;
  };
  detail_lines: {
    enabled: boolean;
    xdog: {
      sigma: number;
      k: number;
      tau: number;
      eps: number;
      phi: number;
    };
    min_length_px: number;
    prune_branch_px: number;
    link_gap_px: number;
    link_max_angle_deg: number;
    width_scale: number;
    width_min: number;
    width_max: number;
    taper_px: number;
    style: "variable" | "stroke";
    color: string;
  };
  output: {
    png_preview_max_side: number;
    pretty: boolean;
  };
  provenance_note: boolean;
}

export const BUILTIN_PRESETS: Record<string, Partial<PipelineParams>> = {
  "Accurate": {
    palette: { k: 64, chroma_weight: 25.0, sample_size: 60000, user_palette: null },
    curves: { smooth_sigma_px: 1.0, rdp_epsilon_px: 0.3, fit_tolerance_px: 0.5, corner_angle_deg: 45, mode: "polygon", decimals: 1 },
    contour_lines: { enabled: false, min_delta_e: 12.0, width_min: 0.8, width_max: 3.0, color_mode: "darker_neighbor", darken: 0.55 },
    detail_lines: { enabled: false, xdog: { sigma: 0.8, k: 1.6, tau: 0.98, eps: 0.02, phi: 10.0 }, min_length_px: 10, prune_branch_px: 6, link_gap_px: 6, link_max_angle_deg: 45, width_scale: 1.0, width_min: 0.6, width_max: 4.0, taper_px: 6, style: "variable", color: "#1b1410" },
  },
  "Clean Ink": {
    palette: { k: 24, chroma_weight: 25.0, sample_size: 60000, user_palette: null },
    curves: { smooth_sigma_px: 1.5, rdp_epsilon_px: 0.6, fit_tolerance_px: 1.0, corner_angle_deg: 50, mode: "bezier", decimals: 1 },
    contour_lines: { enabled: true, min_delta_e: 10.0, width_min: 1.2, width_max: 3.5, color_mode: "darker_neighbor", darken: 0.5 },
    detail_lines: { enabled: true, xdog: { sigma: 0.8, k: 1.6, tau: 0.98, eps: 0.02, phi: 10.0 }, min_length_px: 12, prune_branch_px: 6, link_gap_px: 8, link_max_angle_deg: 45, width_scale: 1.2, width_min: 0.8, width_max: 4.0, taper_px: 8, style: "variable", color: "#1b1410" },
  },
  "Detail": {
    palette: { k: 48, chroma_weight: 25.0, sample_size: 60000, user_palette: null },
    curves: { smooth_sigma_px: 1.2, rdp_epsilon_px: 0.5, fit_tolerance_px: 0.8, corner_angle_deg: 50, mode: "bezier", decimals: 1 },
    contour_lines: { enabled: true, min_delta_e: 12.0, width_min: 0.8, width_max: 3.0, color_mode: "darker_neighbor", darken: 0.55 },
    detail_lines: { enabled: true, xdog: { sigma: 0.8, k: 1.6, tau: 0.98, eps: 0.02, phi: 10.0 }, min_length_px: 8, prune_branch_px: 4, link_gap_px: 6, link_max_angle_deg: 45, width_scale: 1.0, width_min: 0.6, width_max: 4.0, taper_px: 6, style: "variable", color: "#1b1410" },
  },
};

export const DEFAULT_PARAMS: PipelineParams = {
  working_max_side: 2000,
  denoise: { enabled: true, method: "meanshift", sp: 6, sr: 14 },
  palette: { k: 48, chroma_weight: 25.0, sample_size: 60000, user_palette: null },
  regions: { min_area_px: 10, merge_delta_e: 6.0, protect_delta_e: 25.0, protect_max_area_px: 400 },
  curves: { smooth_sigma_px: 1.2, rdp_epsilon_px: 0.5, fit_tolerance_px: 0.8, corner_angle_deg: 50, mode: "bezier", decimals: 1 },
  layers: { grouping: "hue_tone", tone_bands: 3 },
  contour_lines: { enabled: true, min_delta_e: 12.0, width_min: 0.8, width_max: 3.0, color_mode: "darker_neighbor", darken: 0.55 },
  detail_lines: { enabled: true, xdog: { sigma: 0.8, k: 1.6, tau: 0.98, eps: 0.02, phi: 10.0 }, min_length_px: 10, prune_branch_px: 6, link_gap_px: 6, link_max_angle_deg: 45, width_scale: 1.0, width_min: 0.6, width_max: 4.0, taper_px: 6, style: "variable", color: "#1b1410" },
  output: { png_preview_max_side: 1600, pretty: false },
  provenance_note: true,
};

class StateManager {
  public params: PipelineParams = JSON.parse(JSON.stringify(DEFAULT_PARAMS));
  public currentImageFile: File | null = null;
  public currentImageUrl: string | null = null;
  public currentJobId: string | null = null;
  public resultSvg: string | null = null;
  public resultReport: any | null = null;

  public getApiUrl(): string {
    const fromEnv = (import.meta.env.VITE_API_URL as string | undefined) || "";
    return (localStorage.getItem("API_URL") || fromEnv || "http://localhost:10000").replace(/\/+$/, "");
  }

  public setApiUrl(url: string) {
    localStorage.setItem("API_URL", url.replace(/\/+$/, ""));
  }

  public getApiKey(): string {
    return localStorage.getItem("API_KEY") || "";
  }

  public setApiKey(key: string) {
    localStorage.setItem("API_KEY", key.trim());
  }

  public loadPreset(name: string) {
    if (BUILTIN_PRESETS[name]) {
      this.mergeParams(BUILTIN_PRESETS[name]);
      return;
    }
    const saved = localStorage.getItem(`preset_${name}`);
    if (saved) {
      try {
        this.mergeParams(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to parse preset", e);
      }
    }
  }

  public savePreset(name: string) {
    localStorage.setItem(`preset_${name}`, JSON.stringify(this.params));
  }

  private mergeParams(partial: Partial<PipelineParams>) {
    this.params = {
      ...this.params,
      ...partial,
      denoise: { ...this.params.denoise, ...(partial.denoise || {}) },
      palette: { ...this.params.palette, ...(partial.palette || {}) },
      regions: { ...this.params.regions, ...(partial.regions || {}) },
      curves: { ...this.params.curves, ...(partial.curves || {}) },
      layers: { ...this.params.layers, ...(partial.layers || {}) },
      contour_lines: { ...this.params.contour_lines, ...(partial.contour_lines || {}) },
      detail_lines: { ...this.params.detail_lines, ...(partial.detail_lines || {}) },
      output: { ...this.params.output, ...(partial.output || {}) },
    };
  }
}

export const appState = new StateManager();
