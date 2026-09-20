"""
Scikit-Learn ColumnTransformer builder for Appointment No-Show Prediction.
Normalizes numeric predictors and one-hot encodes nominal categoricals
strictly fit on the training split to prevent leakage.
"""

from typing import List, Optional
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder

NUMERIC_FEATURES = [
    "patient_age",
    "appointment_lead_time",
    "previous_appointment_count",
    "previous_no_show_count",
    "sms_reminder_sent",
    "historical_no_show_ratio",
    "has_prior_no_show",
    "frequent_patient",
    "is_weekend",
    "unreminded_long_lead"
]

CATEGORICAL_FEATURES = [
    "appointment_weekday",
    "department",
    "lead_time_bucket",
    "age_cohort"
]


def build_no_show_preprocessing_pipeline(
    numeric_cols: Optional[List[str]] = None,
    categorical_cols: Optional[List[str]] = None
) -> ColumnTransformer:
    """
    Constructs an unfitted ColumnTransformer:
    - StandardScaler on numerical features
    - OneHotEncoder on categorical features
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


# Canonical alias
build_appointment_preprocessing_pipeline = build_no_show_preprocessing_pipeline


def extract_processed_feature_names(preprocessor: ColumnTransformer) -> List[str]:
    """
    Extracts all output feature names from a fitted ColumnTransformer.
    """
    try:
        return list(preprocessor.get_feature_names_out())
    except Exception:
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
