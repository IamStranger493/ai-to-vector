from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class BaseParamsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DenoiseParams(BaseParamsModel):
    enabled: bool = True
    method: Literal["meanshift", "bilateral"] = "meanshift"
    sp: int = Field(default=6, ge=1, le=50)
    sr: int = Field(default=14, ge=1, le=100)


class PaletteParams(BaseParamsModel):
    k: int = Field(default=48, ge=4, le=96)
    chroma_weight: float = Field(default=25.0, ge=1.0, le=100.0)
    sample_size: int = Field(default=60000, ge=1000, le=500000)
    user_palette: Optional[list[str]] = None


class RegionsParams(BaseParamsModel):
    min_area_px: int = Field(default=10, ge=1, le=1000)
    merge_delta_e: float = Field(default=6.0, ge=0.0, le=100.0)
    protect_delta_e: float = Field(default=25.0, ge=0.0, le=100.0)
    protect_max_area_px: int = Field(default=400, ge=1, le=10000)


class CurvesParams(BaseParamsModel):
    smooth_sigma_px: float = Field(default=1.2, ge=0.0, le=3.0)
    rdp_epsilon_px: float = Field(default=0.5, ge=0.0, le=10.0)
    fit_tolerance_px: float = Field(default=0.8, ge=0.2, le=4.0)
    corner_angle_deg: float = Field(default=50.0, ge=20.0, le=120.0)
    mode: Literal["bezier", "polygon"] = "bezier"
    decimals: int = Field(default=1, ge=0, le=4)


class LayersParams(BaseParamsModel):
    grouping: Literal["hue_tone", "segments"] = "hue_tone"
    tone_bands: int = Field(default=3, ge=1, le=4)


class ContourLinesParams(BaseParamsModel):
    enabled: bool = True
    min_delta_e: float = Field(default=12.0, ge=0.0, le=100.0)
    width_min: float = Field(default=0.8, ge=0.1, le=20.0)
    width_max: float = Field(default=3.0, ge=0.1, le=50.0)
    color_mode: Literal["darker_neighbor", "ink"] = "darker_neighbor"
    darken: float = Field(default=0.55, ge=0.0, le=1.0)


class XDoGParams(BaseParamsModel):
    sigma: float = Field(default=0.8, ge=0.1, le=10.0)
    k: float = Field(default=1.6, ge=1.0, le=10.0)
    tau: float = Field(default=0.98, ge=0.0, le=1.0)
    eps: float = Field(default=0.02, ge=0.0, le=1.0)
    phi: float = Field(default=10.0, ge=0.1, le=100.0)


class DetailLinesParams(BaseParamsModel):
    enabled: bool = True
    xdog: XDoGParams = Field(default_factory=XDoGParams)
    min_length_px: int = Field(default=10, ge=1, le=500)
    prune_branch_px: int = Field(default=6, ge=0, le=100)
    link_gap_px: int = Field(default=6, ge=0, le=100)
    link_max_angle_deg: float = Field(default=45.0, ge=0.0, le=180.0)
    width_scale: float = Field(default=1.0, ge=0.1, le=10.0)
    width_min: float = Field(default=0.6, ge=0.1, le=20.0)
    width_max: float = Field(default=4.0, ge=0.1, le=50.0)
    taper_px: int = Field(default=6, ge=0, le=100)
    style: Literal["variable", "stroke"] = "variable"
    color: str = "#1b1410"


class OutputParams(BaseParamsModel):
    png_preview_max_side: int = Field(default=1600, ge=200, le=4000)
    pretty: bool = False


class PipelineParams(BaseParamsModel):
    working_max_side: int = Field(default=2000, ge=800, le=3000)
    denoise: DenoiseParams = Field(default_factory=DenoiseParams)
    palette: PaletteParams = Field(default_factory=PaletteParams)
    regions: RegionsParams = Field(default_factory=RegionsParams)
    curves: CurvesParams = Field(default_factory=CurvesParams)
    layers: LayersParams = Field(default_factory=LayersParams)
    contour_lines: ContourLinesParams = Field(default_factory=ContourLinesParams)
    detail_lines: DetailLinesParams = Field(default_factory=DetailLinesParams)
    output: OutputParams = Field(default_factory=OutputParams)
    provenance_note: bool = True


class JobResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "done", "error"]
    stage: Optional[str] = None
    progress: float = 0.0
    queue_position: int = 0
    error: Optional[str] = None
    created_at: str
    warnings: list[str] = Field(default_factory=list)


class JobCreateResponse(BaseModel):
    job_id: str
