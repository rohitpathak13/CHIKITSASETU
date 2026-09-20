"""
Scikit-Learn Preprocessing Pipeline builder for Patient Risk Prediction.
Ensures zero data leakage by cleanly separating numerical scaling and categorical encoding
to be fit strictly on the training partition.
"""

from typing import List, Tuple
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder


# Canonical feature groupings after cleaning and feature engineering
NUMERIC_FEATURES = [
    "age",
    "bp_systolic",
    "bp_diastolic",
    "glucose",
    "bmi",
    "heart_rate",
    "family_history_diabetes",
    "family_history_hypertension",
    "family_history_heart_disease",
    "pulse_pressure",
    "mean_arterial_pressure",
    "metabolic_risk_score"
]

CATEGORICAL_FEATURES = [
    "gender",
    "smoking_status",
    "hypertension_stage",
    "bmi_category",
    "glucose_category"
]


def build_preprocessing_pipeline(
    numeric_cols: List[str] = None,
    categorical_cols: List[str] = None
) -> ColumnTransformer:
    """
    Constructs an unfitted ColumnTransformer:
    - Standardizes continuous numeric features (Z-score normalizer)
    - One-hot encodes nominal categorical features with unknown value tolerance

    Parameters:
        numeric_cols: List of numerical column names.
        categorical_cols: List of categorical column names.

    Returns:
        Unfitted ColumnTransformer instance.
    """
    num_cols = numeric_cols or NUMERIC_FEATURES
    cat_cols = categorical_cols or CATEGORICAL_FEATURES

    numeric_transformer = StandardScaler()
    categorical_transformer = OneHotEncoder(handle_unknown="ignore", sparse_output=False)

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, num_cols),
            ("cat", categorical_transformer, cat_cols)
        ],
        remainder="drop",
        verbose_feature_names_out=False
    )

    return preprocessor


def extract_processed_feature_names(preprocessor: ColumnTransformer) -> List[str]:
    """
    Extracts all output feature names from a fitted ColumnTransformer.
    """
    try:
        return list(preprocessor.get_feature_names_out())
    except Exception:
        # Fallback manual reconstruction
        names = []
        for name, trans, cols in preprocessor.transformers_:
            if name == "num":
                names.extend(cols)
            elif name == "cat":
                if hasattr(trans, "get_feature_names_out"):
                    names.extend(trans.get_feature_names_out(cols))
                else:
                    names.extend(cols)
        return names
