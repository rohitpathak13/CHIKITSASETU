from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV

NUMERICAL_FEATURES = [
    "age",
    "lead_time_days",
    "appointment_hour",
    "historical_appointments",
    "historical_no_show_ratio",
    "sms_reminder_sent",
]

CATEGORICAL_FEATURES = [
    "gender",
    "day_of_week",
    "department",
]

def build_no_show_pipeline() -> Pipeline:
    """
    Builds a Scikit-Learn Pipeline for Appointment No-Show Prediction
    featuring robust preprocessing and calibrated probability estimates.
    """
    numeric_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERICAL_FEATURES),
            ("cat", categorical_transformer, CATEGORICAL_FEATURES),
        ]
    )

    base_estimator = HistGradientBoostingClassifier(
        max_iter=120,
        max_depth=8,
        min_samples_leaf=20,
        random_state=42
    )

    # Calibrated probability output
    calibrated_classifier = CalibratedClassifierCV(
        estimator=base_estimator,
        method="sigmoid",
        cv=3
    )

    model_pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", calibrated_classifier),
    ])

    return model_pipeline
