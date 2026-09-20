"""
Model Registry and Artifact Persistence for Appointment No-Show Prediction.
Stores joblib serialized Pipeline, ColumnTransformer, and JSON model provenance metadata.
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
PIPELINE_ARTIFACT_NAME = "best_no_show_model.joblib"
PREPROCESSOR_ARTIFACT_NAME = "preprocessor.joblib"
MODEL_CARD_NAME = "model_card.json"

OPERATIONAL_DISCLAIMER = (
    "DISCLAIMER: This machine learning model is an operational scheduling decision-support tool "
    "intended strictly for demonstration and attendance risk triage. It DOES NOT make clinical diagnoses "
    "or provide medical claims. All patient scheduling and healthcare decisions must be managed by authorized staff."
)


@dataclass
class NoShowModelCard:
    model_name: str
    model_version: str
    algorithm: str
    creation_date: str
    training_sample_count: int
    test_sample_count: int
    input_features: list
    evaluation_metrics: Dict[str, Any]
    imputation_defaults: Dict[str, Any]
    disclaimer: str = OPERATIONAL_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, file_path: Path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, file_path: Path) -> "NoShowModelCard":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)


def save_no_show_artifacts(
    pipeline: Pipeline,
    preprocessor: ColumnTransformer,
    model_card: NoShowModelCard,
    target_dir: Optional[Path] = None
) -> Dict[str, Path]:
    """
    Persists trained no-show pipeline, preprocessor, and model card metadata.
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


def load_no_show_artifacts(
    source_dir: Optional[Path] = None
) -> Tuple[Pipeline, ColumnTransformer, NoShowModelCard]:
    """
    Loads serialized no-show pipeline, preprocessor, and model card.
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
    model_card = NoShowModelCard.load(card_path)

    return pipeline, preprocessor, model_card


# Alias for compatibility
save_no_show_model_artifacts = save_no_show_artifacts
