"""
Model Registry and Artifact Management for Patient Risk Prediction.
Handles joblib serialization and deserialization of the trained Scikit-Learn pipeline,
standalone preprocessor, and JSON model card metadata with medical disclaimers.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import joblib
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer

CURRENT_DIR = Path(__file__).resolve().parent
SAVED_MODELS_DIR = CURRENT_DIR / "saved_models"
PIPELINE_ARTIFACT_NAME = "best_risk_model.joblib"
PREPROCESSOR_ARTIFACT_NAME = "preprocessor.joblib"
MODEL_CARD_NAME = "model_card.json"

MEDICAL_DISCLAIMER = (
    "DISCLAIMER: This machine learning model is intended strictly for educational and operational "
    "demonstration purposes. It DOES NOT provide medical diagnosis, clinical treatment advice, or "
    "therapeutic management. All patient assessments must be made by licensed medical practitioners."
)


@dataclass
class ModelCard:
    model_name: str
    model_version: str
    algorithm: str
    creation_date: str
    training_sample_count: int
    test_sample_count: int
    target_classes: list
    input_features: list
    evaluation_metrics: Dict[str, Any]
    imputation_defaults: Dict[str, Any]
    disclaimer: str = MEDICAL_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, file_path: Path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, file_path: Path) -> "ModelCard":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)


def save_model_artifacts(
    pipeline: Pipeline,
    preprocessor: ColumnTransformer,
    model_card: ModelCard,
    target_dir: Optional[Path] = None
) -> Dict[str, Path]:
    """
    Serializes best model pipeline, preprocessor, and model card metadata.

    Parameters:
        pipeline: Complete end-to-end fitted Scikit-Learn Pipeline.
        preprocessor: Fitted ColumnTransformer preprocessor.
        model_card: ModelCard metadata object.
        target_dir: Directory where artifacts are saved.

    Returns:
        Dict mapping artifact keys to their absolute Path locations.
    """
    dest_dir = target_dir or SAVED_MODELS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    pipeline_path = dest_dir / PIPELINE_ARTIFACT_NAME
    preprocessor_path = dest_dir / PREPROCESSOR_ARTIFACT_NAME
    card_path = dest_dir / MODEL_CARD_NAME

    joblib.dump(pipeline, pipeline_path)
    joblib.dump(preprocessor, preprocessor_path)
    model_card.save(card_path)

    return {
        "pipeline_path": pipeline_path,
        "preprocessor_path": preprocessor_path,
        "model_card_path": card_path
    }


def load_model_artifacts(
    source_dir: Optional[Path] = None
) -> Tuple[Pipeline, ColumnTransformer, ModelCard]:
    """
    Deserializes the trained risk model pipeline, preprocessor, and model card.

    Parameters:
        source_dir: Directory containing serialized artifacts.

    Returns:
        Tuple of (pipeline, preprocessor, model_card).
    """
    load_dir = source_dir or SAVED_MODELS_DIR
    pipeline_path = load_dir / PIPELINE_ARTIFACT_NAME
    preprocessor_path = load_dir / PREPROCESSOR_ARTIFACT_NAME
    card_path = load_dir / MODEL_CARD_NAME

    if not pipeline_path.exists():
        raise FileNotFoundError(f"Model pipeline not found at {pipeline_path}. Run training first.")
    if not preprocessor_path.exists():
        raise FileNotFoundError(f"Preprocessor not found at {preprocessor_path}. Run training first.")
    if not card_path.exists():
        raise FileNotFoundError(f"Model card not found at {card_path}.")

    pipeline = joblib.load(pipeline_path)
    preprocessor = joblib.load(preprocessor_path)
    model_card = ModelCard.load(card_path)

    return pipeline, preprocessor, model_card
