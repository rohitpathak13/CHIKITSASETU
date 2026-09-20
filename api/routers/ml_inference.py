import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from core.config import settings
from api.dependencies import get_current_user
from api.schemas.ml import (
    ReadmissionPredictRequest, ReadmissionPredictResponse,
    NoShowPredictRequest, NoShowPredictResponse
)
from ml.inference.predictors import readmission_predictor, no_show_predictor

router = APIRouter(prefix="/predict", tags=["Machine Learning Inference"])

@router.post("/readmission", response_model=ReadmissionPredictResponse)
def predict_readmission(payload: ReadmissionPredictRequest):
    """
    Real-time 30-day inpatient readmission and clinical deterioration scoring.
    """
    data_dict = payload.model_dump()
    result = readmission_predictor.predict(data_dict)
    return ReadmissionPredictResponse(**result)

@router.post("/no-show", response_model=NoShowPredictResponse)
def predict_no_show(payload: NoShowPredictRequest):
    """
    Real-time appointment attendance probability and triage prediction.
    """
    data_dict = payload.model_dump()
    result = no_show_predictor.predict(data_dict)
    return NoShowPredictResponse(**result)

@router.get("/metadata")
def get_model_metadata():
    """
    Returns training benchmarks, algorithms, and evaluation metrics for deployed ML pipelines.
    """
    meta_path = settings.ML_ARTIFACTS_DIR / "model_metadata.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r") as f:
                return json.load(f)
        except Exception:
            return {"error": "Failed to read metadata file"}
    return {"message": "No model metadata currently available"}
