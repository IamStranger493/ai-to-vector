import { appState } from "../state";

export function initParamsPanel(onChange: () => void) {
  const container = document.getElementById("params-container");
  if (!container) return;

  container.innerHTML = `
    <!-- Detail & Scale Section -->
    <section class="panel-section">
      <h3 class="section-title">Detail & Resolution</h3>
      
      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-working-size" title="Working resolution longest dimension (800–3000 px)">Max Working Size</label>
          <span id="val-working-size" class="control-value">2000 px</span>
        </div>
        <input type="range" id="param-working-size" min="800" max="3000" step="100" class="styled-range" value="${appState.params.working_max_side}">
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-k" title="Palette color count (4–96)">Color Palette (k)</label>
          <span id="val-k" class="control-value">48</span>
        </div>
        <input type="range" id="param-k" min="4" max="96" step="2" class="styled-range" value="${appState.params.palette.k}">
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-min-area" title="Minimum region area in pixels (1–50 px)">Min Region Area</label>
          <span id="val-min-area" class="control-value">10 px</span>
        </div>
        <input type="range" id="param-min-area" min="1" max="50" step="1" class="styled-range" value="${appState.params.regions.min_area_px}">
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-merge-delta" title="Max Delta-E color distance for merging tiny shapes">Merge Delta E</label>
          <span id="val-merge-delta" class="control-value">6.0</span>
        </div>
        <input type="range" id="param-merge-delta" min="0" max="25" step="0.5" class="styled-range" value="${appState.params.regions.merge_delta_e}">
      </div>
    </section>

    <!-- Curves & Geometry Section -->
    <section class="panel-section">
      <h3 class="section-title">Curves & Smoothing</h3>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-curve-mode" title="Bezier cubic splines vs exact Polygon mode">Curve Mode</label>
        </div>
        <select id="param-curve-mode" class="styled-select">
          <option value="bezier">Cubic Bezier (Smooth & Compact)</option>
          <option value="polygon">Polygon (Exact & Safe)</option>
        </select>
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-sigma" title="Gaussian smoothing along shared boundary lattice">Smooth Sigma</label>
          <span id="val-sigma" class="control-value">1.2 px</span>
        </div>
        <input type="range" id="param-sigma" min="0" max="3" step="0.1" class="styled-range" value="${appState.params.curves.smooth_sigma_px}">
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-fit-tol" title="Schneider Bezier fitting tolerance (0.2–4 px)">Fit Tolerance</label>
          <span id="val-fit-tol" class="control-value">0.8 px</span>
        </div>
        <input type="range" id="param-fit-tol" min="0.2" max="4.0" step="0.1" class="styled-range" value="${appState.params.curves.fit_tolerance_px}">
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-corner-deg" title="Sharp corner detection threshold (20–120 deg)">Corner Angle</label>
          <span id="val-corner-deg" class="control-value">50°</span>
        </div>
        <input type="range" id="param-corner-deg" min="20" max="120" step="5" class="styled-range" value="${appState.params.curves.corner_angle_deg}">
      </div>
    </section>

    <!-- Inking / Contour Lines Section -->
    <section class="panel-section">
      <div class="control-label-row" style="margin-bottom: 0.5rem">
        <h3 class="section-title" style="margin: 0">Contour Ink Lines</h3>
        <label class="checkbox-row" style="margin: 0">
          <input type="checkbox" id="param-contour-enable" ${appState.params.contour_lines.enabled ? "checked" : ""} />
          <span style="font-size: 0.75rem">Enable</span>
        </label>
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-contour-width" title="Contour line thickness range">Stroke Width</label>
          <span id="val-contour-width" class="control-value">0.8 – 3.0 px</span>
        </div>
        <input type="range" id="param-contour-width-max" min="1.0" max="8.0" step="0.5" class="styled-range" value="${appState.params.contour_lines.width_max}">
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-contour-darken" title="Darken factor for darker neighbor ink (0.1–1.0)">Darken Factor</label>
          <span id="val-contour-darken" class="control-value">0.55</span>
        </div>
        <input type="range" id="param-contour-darken" min="0.1" max="1.0" step="0.05" class="styled-range" value="${appState.params.contour_lines.darken}">
      </div>
    </section>

    <!-- Detail Lines Section -->
    <section class="panel-section">
      <div class="control-label-row" style="margin-bottom: 0.5rem">
        <h3 class="section-title" style="margin: 0">Detail Inking (Hair/Folds)</h3>
        <label class="checkbox-row" style="margin: 0">
          <input type="checkbox" id="param-detail-enable" ${appState.params.detail_lines.enabled ? "checked" : ""} />
          <span style="font-size: 0.75rem">Enable</span>
        </label>
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-detail-style" title="Variable width outline vs center-line stroke">Detail Style</label>
        </div>
        <select id="param-detail-style" class="styled-select">
          <option value="variable">Variable Width Outline (Expressive)</option>
          <option value="stroke">Center-Line Stroke (Editable)</option>
        </select>
      </div>

      <div class="control-row">
        <div class="control-label-row">
          <label class="control-label" for="param-detail-scale" title="Multiplier for detail line thickness">Detail Thickness Scale</label>
          <span id="val-detail-scale" class="control-value">1.0x</span>
        </div>
        <input type="range" id="param-detail-scale" min="0.5" max="3.0" step="0.1" class="styled-range" value="${appState.params.detail_lines.width_scale}">
      </div>
    </section>

    <!-- Provenance Note Checkbox (Section 6 & 9.2: Default ON) -->
    <section class="panel-section">
      <label class="checkbox-row">
        <input type="checkbox" id="param-provenance" ${appState.params.provenance_note ? "checked" : ""} />
        <span class="control-label" style="font-weight: 500">Add provenance note to file metadata</span>
      </label>
      <span class="field-hint" style="font-size: 0.75rem; color: var(--text-dim); display: block">
        Honest provenance note embedded in SVG &lt;desc&gt; and &lt;metadata&gt; per specification.
      </span>
    </section>
  `;

  bindControls(onChange);
}

function bindControls(onChange: () => void) {
  const sync = (id: string, valId: string, transform: (v: number) => string, updater: (v: number) => void) => {
    const input = document.getElementById(id) as HTMLInputElement;
    const badge = document.getElementById(valId) as HTMLElement;
    if (!input || !badge) return;
    // Show the real current value immediately (presets change slider values, labels were hard-coded)
    badge.textContent = transform(parseFloat(input.value));
    input.addEventListener("input", () => {
      const num = parseFloat(input.value);
      badge.textContent = transform(num);
      updater(num);
      onChange();
    });
  };

  sync("param-working-size", "val-working-size", (v) => `${v} px`, (v) => { appState.params.working_max_side = v; });
  sync("param-k", "val-k", (v) => `${v}`, (v) => { appState.params.palette.k = v; });
  sync("param-min-area", "val-min-area", (v) => `${v} px`, (v) => { appState.params.regions.min_area_px = v; });
  sync("param-merge-delta", "val-merge-delta", (v) => `${v.toFixed(1)}`, (v) => { appState.params.regions.merge_delta_e = v; });
  sync("param-sigma", "val-sigma", (v) => `${v.toFixed(1)} px`, (v) => { appState.params.curves.smooth_sigma_px = v; });
  sync("param-fit-tol", "val-fit-tol", (v) => `${v.toFixed(1)} px`, (v) => { appState.params.curves.fit_tolerance_px = v; });
  sync("param-corner-deg", "val-corner-deg", (v) => `${v}°`, (v) => { appState.params.curves.corner_angle_deg = v; });
  sync("param-contour-width-max", "val-contour-width", (v) => `0.8 – ${v.toFixed(1)} px`, (v) => { appState.params.contour_lines.width_max = v; });
  sync("param-contour-darken", "val-contour-darken", (v) => `${v.toFixed(2)}`, (v) => { appState.params.contour_lines.darken = v; });
  sync("param-detail-scale", "val-detail-scale", (v) => `${v.toFixed(1)}x`, (v) => { appState.params.detail_lines.width_scale = v; });

  const curveMode = document.getElementById("param-curve-mode") as HTMLSelectElement;
  if (curveMode) {
    curveMode.value = appState.params.curves.mode;
    curveMode.addEventListener("change", () => {
      appState.params.curves.mode = curveMode.value as any;
      onChange();
    });
  }

  const detailStyle = document.getElementById("param-detail-style") as HTMLSelectElement;
  if (detailStyle) {
    detailStyle.value = appState.params.detail_lines.style;
    detailStyle.addEventListener("change", () => {
      appState.params.detail_lines.style = detailStyle.value as any;
      onChange();
    });
  }

  const contourEnable = document.getElementById("param-contour-enable") as HTMLInputElement;
  if (contourEnable) {
    contourEnable.addEventListener("change", () => {
      appState.params.contour_lines.enabled = contourEnable.checked;
      onChange();
    });
  }

  const detailEnable = document.getElementById("param-detail-enable") as HTMLInputElement;
  if (detailEnable) {
    detailEnable.addEventListener("change", () => {
      appState.params.detail_lines.enabled = detailEnable.checked;
      onChange();
    });
  }

  const provenance = document.getElementById("param-provenance") as HTMLInputElement;
  if (provenance) {
    provenance.addEventListener("change", () => {
      appState.params.provenance_note = provenance.checked;
      onChange();
    });
  }
}
