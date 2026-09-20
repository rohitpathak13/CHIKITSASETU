"""
Training and Model Selection Pipeline for Appointment No-Show Prediction.
Trains, calibrates, and benchmarks Logistic Regression, Random Forest, and Gradient Boosting.
Guarantees zero data leakage with a strict split-first architecture.
"""

from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV

from ml.no_show_prediction.datasets.loader import (
    load_no_show_dataset,
    TARGET_COLUMN
)
from ml.no_show_prediction.preprocessing.cleaner import clean_no_show_data
from ml.no_show_prediction.preprocessing.feature_engineer import engineer_no_show_features
from ml.no_show_prediction.preprocessing.pipeline import build_no_show_preprocessing_pipeline
from ml.no_show_prediction.evaluation.evaluator import (
    evaluate_no_show_models,
    generate_no_show_comparison_markdown
)
from ml.no_show_prediction.evaluation.metrics import NoShowEvaluationResult
from ml.no_show_prediction.models.model_registry import (
    save_no_show_artifacts,
    NoShowModelCard,
    SAVED_MODELS_DIR
)


class NoShowModelTrainer:
    """
    Orchestrates data preparation, multi-model training, calibration,
    comparative evaluation, and artifact serialization.
    """

    def __init__(
        self,
        test_size: float = 0.20,
        random_state: int = 42,
        artifacts_dir: Optional[Path] = None,
        models_dir: Optional[Path] = None,
        n_samples: Optional[int] = None
    ):
        self.test_size = test_size
        self.random_state = random_state
        self.artifacts_dir = artifacts_dir or models_dir or SAVED_MODELS_DIR
        self.n_samples = n_samples

        self.imputation_stats: Dict[str, Any] = {}
        self.models: Dict[str, Pipeline] = {}
        self.evaluation_results: List[NoShowEvaluationResult] = []
        self.best_model_name: Optional[str] = None
        self.best_pipeline: Optional[Pipeline] = None
        self.best_metrics: Optional[NoShowEvaluationResult] = None

    def run_pipeline(self, save_artifacts: bool = True):
        """Convenience method returning trainer instance after running pipeline."""
        from ml.no_show_prediction.datasets.loader import generate_synthetic_no_show_data
        df = generate_synthetic_no_show_data(n_samples=self.n_samples, random_state=self.random_state) if self.n_samples else None
        self.run_training_pipeline(df=df, save_best=save_artifacts)
        return self

    def run_training_pipeline(
        self,
        df: Optional[pd.DataFrame] = None,
        save_best: bool = True
    ) -> Tuple[Pipeline, List[NoShowEvaluationResult]]:
        """
        Executes complete training and model selection lifecycle:
        1. Stratified train/test split.
        2. Imputation statistics learned strictly on X_train.
        3. Domain feature engineering.
        4. Pipeline fitting for Logistic Regression, Random Forest, and Gradient Boosting.
        5. Calibrated probability evaluation.
        6. Best model selection and serialization.
        """
        raw_df = df if df is not None else load_no_show_dataset()

        if TARGET_COLUMN not in raw_df.columns:
            raise ValueError(f"Target column '{TARGET_COLUMN}' not found in dataframe.")

        X = raw_df.drop(columns=[TARGET_COLUMN])
        y = raw_df[TARGET_COLUMN].astype(int)

        # 1. Stratified Train / Test Split
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=self.test_size,
            random_state=self.random_state,
            stratify=y
        )

        # 2. Cleaning & Imputation on X_train
        X_train_cleaned, self.imputation_stats = clean_no_show_data(
            X_train,
            is_training=True
        )
        # Apply learned stats to X_test (no leakage)
        X_test_cleaned, _ = clean_no_show_data(
            X_test,
            imputation_stats=self.imputation_stats,
            is_training=False
        )

        # 3. Feature Engineering
        X_train_feat = engineer_no_show_features(X_train_cleaned)
        X_test_feat = engineer_no_show_features(X_test_cleaned)

        # 4. Candidate Classifiers
        candidate_classifiers = {
            "Logistic Regression": LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=self.random_state
            ),
            "Random Forest": RandomForestClassifier(
                n_estimators=120,
                max_depth=8,
                min_samples_split=5,
                class_weight="balanced",
                random_state=self.random_state
            ),
            "Gradient Boosting": GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.10,
                max_depth=4,
                subsample=0.85,
                random_state=self.random_state
            )
        }

        # 5. Fit each Candidate Pipeline
        self.models = {}
        for name, clf in candidate_classifiers.items():
            preprocessor = build_no_show_preprocessing_pipeline()
            # Wrap in CalibratedClassifierCV to guarantee accurate probabilities
            calibrated_clf = CalibratedClassifierCV(
                estimator=clf,
                method="sigmoid",
                cv=3
            )
            pipeline = Pipeline([
                ("preprocessor", preprocessor),
                ("classifier", calibrated_clf)
            ])
            pipeline.fit(X_train_feat, y_train)
            self.models[name] = pipeline

        # 6. Comparative Evaluation
        self.evaluation_results = evaluate_no_show_models(
            trained_pipelines=self.models,
            X_test=X_test_feat,
            y_test=y_test
        )

        # 7. Model Selection (Primary criterion: ROC-AUC, secondary: F1-score)
        best_res = max(self.evaluation_results, key=lambda r: (r.roc_auc or 0.0, r.f1_score))
        self.best_model_name = best_res.model_name
        self.best_pipeline = self.models[self.best_model_name]
        self.best_metrics = best_res

        # 8. Save Selected Model and Preprocessor
        if save_best:
            best_preprocessor = self.best_pipeline.named_steps["preprocessor"]
            card = NoShowModelCard(
                model_name="Appointment No-Show Predictor",
                model_version="1.0.0",
                algorithm=self.best_model_name,
                creation_date=datetime.now(timezone.utc).isoformat(),
                training_sample_count=len(X_train),
                test_sample_count=len(X_test),
                input_features=list(X.columns),
                evaluation_metrics=best_res.to_dict(),
                imputation_defaults=self.imputation_stats
            )
            save_no_show_artifacts(
                pipeline=self.best_pipeline,
                preprocessor=best_preprocessor,
                model_card=card,
                target_dir=self.artifacts_dir
            )

        return self.best_pipeline, self.evaluation_results


def train_and_evaluate_no_show_pipeline(
    df: Optional[pd.DataFrame] = None,
    save_best: bool = True
) -> Tuple[Pipeline, List[NoShowEvaluationResult], str]:
    """
    Convenience function for end-to-end appointment no-show model training.
    """
    trainer = NoShowModelTrainer()
    best_pipeline, results = trainer.run_training_pipeline(df=df, save_best=save_best)
    report_md = generate_no_show_comparison_markdown(results)
    return best_pipeline, results, report_md


# Aliases for compatibility
AppointmentNoShowTrainer = NoShowModelTrainer
