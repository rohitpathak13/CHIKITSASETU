"""
Model Training and Comparison Pipeline for Patient Risk Prediction.
Trains Logistic Regression, Random Forest, and Gradient Boosting models,
benchmarks them on a held-out test split, and saves the best model.
Guarantees zero data leakage through strict split-first design.
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

from ml.risk_prediction.datasets.loader import load_patient_risk_dataset, TARGET_COLUMN
from ml.risk_prediction.preprocessing.cleaner import clean_patient_risk_data
from ml.risk_prediction.preprocessing.feature_engineer import engineer_patient_risk_features
from ml.risk_prediction.preprocessing.pipeline import build_preprocessing_pipeline
from ml.risk_prediction.evaluation.evaluator import evaluate_model_suite, generate_comparison_markdown
from ml.risk_prediction.evaluation.metrics import EvaluationResult
from ml.risk_prediction.models.model_registry import (
    save_model_artifacts,
    ModelCard,
    SAVED_MODELS_DIR
)


class RiskModelTrainer:
    """
    Orchestrates the leak-free data preparation, model training,
    comparative evaluation, and artifact serialization.
    """

    def __init__(
        self,
        test_size: float = 0.20,
        random_state: int = 42,
        artifacts_dir: Optional[Path] = None
    ):
        self.test_size = test_size
        self.random_state = random_state
        self.artifacts_dir = artifacts_dir or SAVED_MODELS_DIR

        self.imputation_stats: Dict[str, Any] = {}
        self.models: Dict[str, Pipeline] = {}
        self.evaluation_results: List[EvaluationResult] = []
        self.best_model_name: Optional[str] = None
        self.best_pipeline: Optional[Pipeline] = None
        self.best_metrics: Optional[EvaluationResult] = None

    def run_training_pipeline(
        self,
        df: Optional[pd.DataFrame] = None,
        save_best: bool = True
    ) -> Tuple[Pipeline, List[EvaluationResult]]:
        """
        Executes complete training and model selection lifecycle:
        1. Train/Test stratified split before any statistical preprocessing.
        2. Imputation statistics learned strictly on X_train, then applied to X_test.
        3. Domain feature engineering.
        4. Pipeline fitting for Logistic Regression, Random Forest, Gradient Boosting.
        5. Evaluation and comparative benchmarking.
        6. Best model serialization.

        Returns:
            Tuple of (best_fitted_pipeline, evaluation_results_list)
        """
        raw_df = df if df is not None else load_patient_risk_dataset()
        
        if TARGET_COLUMN not in raw_df.columns:
            raise ValueError(f"Target column '{TARGET_COLUMN}' not found in dataframe.")

        X = raw_df.drop(columns=[TARGET_COLUMN])
        y = raw_df[TARGET_COLUMN]

        # 1. Stratified Train / Test Split (Strictly before any preprocessing to avoid leakage)
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=self.test_size,
            random_state=self.random_state,
            stratify=y
        )

        # 2. Data Cleaning & Imputation (Stats computed strictly on X_train)
        X_train_cleaned, self.imputation_stats = clean_patient_risk_data(
            X_train,
            is_training=True
        )
        # Apply learned stats to test set
        X_test_cleaned, _ = clean_patient_risk_data(
            X_test,
            imputation_stats=self.imputation_stats,
            is_training=False
        )

        # 3. Feature Engineering
        X_train_feat = engineer_patient_risk_features(X_train_cleaned)
        X_test_feat = engineer_patient_risk_features(X_test_cleaned)

        # 4. Instantiate Candidate Classifiers
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

        # 5. Train each Candidate Pipeline
        self.models = {}
        for name, clf in candidate_classifiers.items():
            preprocessor = build_preprocessing_pipeline()
            pipeline = Pipeline([
                ("preprocessor", preprocessor),
                ("classifier", clf)
            ])
            pipeline.fit(X_train_feat, y_train)
            self.models[name] = pipeline

        # 6. Comprehensive Evaluation
        self.evaluation_results = evaluate_model_suite(
            trained_pipelines=self.models,
            X_test=X_test_feat,
            y_test=y_test,
            labels=["Low", "Medium", "High"]
        )

        # 7. Model Selection (Primary criterion: F1-Weighted score)
        best_res = max(self.evaluation_results, key=lambda r: r.f1_weighted)
        self.best_model_name = best_res.model_name
        self.best_pipeline = self.models[self.best_model_name]
        self.best_metrics = best_res

        # 8. Save Selected Model and Preprocessing Pipeline
        if save_best:
            best_preprocessor = self.best_pipeline.named_steps["preprocessor"]
            card = ModelCard(
                model_name="Patient Risk Classifier",
                model_version="1.0.0",
                algorithm=self.best_model_name,
                creation_date=datetime.now(timezone.utc).isoformat(),
                training_sample_count=len(X_train),
                test_sample_count=len(X_test),
                target_classes=["Low", "Medium", "High"],
                input_features=list(X.columns),
                evaluation_metrics=best_res.to_dict(),
                imputation_defaults=self.imputation_stats
            )
            save_model_artifacts(
                pipeline=self.best_pipeline,
                preprocessor=best_preprocessor,
                model_card=card,
                target_dir=self.artifacts_dir
            )

        return self.best_pipeline, self.evaluation_results


def train_and_evaluate_pipeline(
    df: Optional[pd.DataFrame] = None,
    save_best: bool = True
) -> Tuple[Pipeline, List[EvaluationResult], str]:
    """
    Convenience functional interface for end-to-end model training.
    Returns: (best_pipeline, evaluation_results, comparison_markdown_table)
    """
    trainer = RiskModelTrainer()
    best_pipeline, results = trainer.run_training_pipeline(df=df, save_best=save_best)
    report_md = generate_comparison_markdown(results)
    return best_pipeline, results, report_md
