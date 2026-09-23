"""
FastAPI Router for Machine Learning Inference and Clinical Decision Support.
Exposes real-time patient risk stratification endpoints with Pydantic validation
and non-diagnostic educational disclaimers.
"""

from typing import Dict, Any
import logging
from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

logger = logging.getLogger(__name__)

from backend.fastapi_service.schemas.ml import (
    PatientRiskPredictRequest,
    PatientRiskPredictResponse,
    NoShowPredictRequest,
    NoShowPredictResponse
)
from ml.risk_prediction.predictions.predictor import (
    PatientRiskPredictor,
    PatientRiskPredictionResult
)
from ml.no_show_prediction.predictions.predictor import (
    NoShowPredictorService,
    NoShowPredictionResult
)

router = APIRouter(prefix="/ml", tags=["Machine Learning - Clinical & Operational Risk"])

# Singleton predictor instances
_risk_predictor: PatientRiskPredictor = None
_no_show_predictor: NoShowPredictorService = None


def get_risk_predictor() -> PatientRiskPredictor:
    """Lazy loader for PatientRiskPredictor singleton."""
    global _risk_predictor
    if _risk_predictor is None:
        try:
            _risk_predictor = PatientRiskPredictor()
        except Exception as e:
            logger.exception("Failed to load patient risk predictor: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Patient risk model artifacts could not be loaded."
            )
    return _risk_predictor


@router.post(
    "/risk-prediction",
    response_model=PatientRiskPredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict Patient Risk Category",
    description=(
        "Calculates multi-class patient clinical risk tier ('Low', 'Medium', 'High') "
        "along with confidence probability distributions and key physiological drivers. "
        "DISCLAIMER: For educational/operational decision-support only. Not a medical diagnosis."
    )
)
def predict_patient_risk(payload: PatientRiskPredictRequest) -> PatientRiskPredictResponse:
    """
    Executes real-time patient risk inference across demographics, vitals,
    metabolic parameters, lifestyle factors, and family history.
    """
    try:
        predictor = get_risk_predictor()
        patient_dict = payload.model_dump()

        # Execute model inference
        result: PatientRiskPredictionResult = predictor.predict_single(patient_dict)

        return PatientRiskPredictResponse(
            risk_category=result.risk_category,
            confidence=result.confidence,
            probabilities=result.probabilities,
            model_version=result.model_version,
            algorithm=result.algorithm,
            risk_factors=result.risk_factors,
            is_medical_diagnosis=False,
            disclaimer=result.disclaimer
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid clinical feature data: {str(ve)}"
        )
    except Exception as e:
        logger.exception("Patient risk inference error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Patient risk inference failed. Please try again."
        )


@router.get("/risk-prediction/model-card", summary="Retrieve Patient Risk Model Card")
def get_risk_model_card() -> Dict[str, Any]:
    """
    Returns training provenance, algorithm hyperparameters, evaluation benchmarks,
    and clinical disclaimers for the active Patient Risk model.
    """
    try:
        predictor = get_risk_predictor()
        if predictor.model_card:
            return predictor.model_card.to_dict()
        return {"message": "Model card metadata not available"}
    except Exception as e:
        logger.exception("Failed to load patient risk model card: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load model card."
        )


def get_no_show_predictor() -> NoShowPredictorService:
    """Lazy loader for NoShowPredictorService singleton."""
    global _no_show_predictor
    if _no_show_predictor is None:
        try:
            _no_show_predictor = NoShowPredictorService()
        except Exception as e:
            logger.exception("Failed to load no-show predictor: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Appointment no-show model artifacts could not be loaded."
            )
    return _no_show_predictor


@router.post(
    "/no-show-prediction",
    response_model=NoShowPredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict Appointment Attendance & No-Show Risk",
    description=(
        "Calculates calibrated probability of patient appointment no-show, operational "
        "triage tier ('Low', 'Medium', 'High'), friction drivers, and reminder recommendations. "
        "DISCLAIMER: Operational decision-support tool. Does NOT make clinical diagnoses."
    )
)
def predict_appointment_no_show(payload: NoShowPredictRequest) -> NoShowPredictResponse:
    """
    Executes real-time attendance likelihood estimation across appointment lead times,
    weekdays, prior attendance records, and clinical department.
    """
    try:
        predictor = get_no_show_predictor()
        appt_dict = {
            "patient_age": payload.get_canonical_age(),
            "appointment_weekday": payload.get_canonical_weekday(),
            "appointment_lead_time": payload.get_canonical_lead_time(),
            "previous_appointment_count": payload.get_canonical_previous_appointments(),
            "previous_no_show_count": payload.get_canonical_previous_no_shows(),
            "department": payload.department,
            "sms_reminder_sent": payload.sms_reminder_sent
        }
        res: NoShowPredictionResult = predictor.predict_single(appt_dict)

        return NoShowPredictResponse(
            no_show_probability=res.no_show_probability,
            no_show_percentage=round(res.no_show_probability * 100, 1),
            no_show_prediction=res.no_show_prediction,
            risk_tier=res.risk_tier,
            confidence=res.confidence,
            recommendation=res.recommendation,
            risk_factors=res.risk_factors,
            model_version=res.model_version,
            algorithm=res.algorithm,
            is_medical_diagnosis=False,
            disclaimer=res.disclaimer
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid appointment feature data: {str(ve)}"
        )
    except Exception as e:
        logger.exception("Appointment no-show inference error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Appointment no-show inference failed. Please try again."
        )


@router.get("/no-show-prediction/model-card", summary="Retrieve Appointment No-Show Model Card")
def get_no_show_model_card() -> Dict[str, Any]:
    """
    Returns training provenance, algorithm hyperparameters, evaluation benchmarks,
    and operational disclaimers for the active Appointment No-Show model.
    """
    try:
        predictor = get_no_show_predictor()
        if predictor.model_card:
            return predictor.model_card.to_dict()
        return {"message": "Model card metadata not available"}
    except Exception as e:
        logger.exception("Failed to load no-show model card: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load model card."
        )
