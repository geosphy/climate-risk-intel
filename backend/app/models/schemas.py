"""
Pydantic data models for ClimateRisk Intel API.
Defines all request and response shapes.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


# --- Request Models ---

class RiskRequest(BaseModel):
    address: str = Field(
        ...,
        description="Street address, city/state, or zip/pin code",
        examples=["Houston, TX 77002", "77002", "Miami, FL"]
    )
    asset_type: Literal["building", "land", "infrastructure"] = Field(
        default="building",
        description="Type of physical asset being assessed"
    )


# --- Sub-models ---

class HazardScore(BaseModel):
    score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Risk score from 0.0 (no risk) to 1.0 (extreme risk)"
    )
    level: Literal["Low", "Medium", "High", "Extreme"] = Field(
        ..., description="Human-readable risk level"
    )
    confidence: Literal["Low", "Medium", "High"] = Field(
        ..., description="Confidence in the risk assessment"
    )
    details: dict = Field(
        default_factory=dict,
        description="Source-specific metadata and raw values"
    )


class GeocodeResult(BaseModel):
    latitude: float
    longitude: float
    canonical_address: str
    country_code: str = "US"


# --- Response Models ---

class RiskReport(BaseModel):
    address: str
    canonical_address: str
    latitude: float
    longitude: float

    flood_risk: HazardScore
    heat_risk: HazardScore
    storm_risk: HazardScore
    overall_risk: HazardScore

    ai_narrative: str = Field(
        default="",
        description="AI-generated plain English risk summary"
    )
    data_sources: list[str] = Field(
        default_factory=list,
        description="List of data sources used in this assessment"
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Any warnings about data quality or coverage"
    )


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    services: dict[str, bool]


# --- Scoring helper ---

def score_to_level(score: float) -> Literal["Low", "Medium", "High", "Extreme"]:
    if score >= 0.85:
        return "Extreme"
    elif score >= 0.65:
        return "High"
    elif score >= 0.45:
        return "Medium"
    else:
        return "Low"
