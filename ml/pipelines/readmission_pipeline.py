from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.ensemble import RandomForestClassifier

NUMERICAL_FEATURES = [
    "age",
    "length_of_stay_days",
    "previous_admissions_12m",
    "chronic_conditions_count",
    "abnormal_lab_count",
    "vital_instability_index",
    "medication_count",
    "high_risk_medication_flag",
]

CATEGORICAL_FEATURES = [
    "gender",
    "admission_type",
    "ward_type",
]

def build_readmission_pipeline() -> Pipeline:
    """
    Builds a self-contained Scikit-Learn Pipeline combining imputation,
    feature transformations, and an ensemble classifier.
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

    classifier = RandomForestClassifier(
        n_estimators=150,
        max_depth=12,
        min_samples_split=6,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )

    model_pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", classifier),
    ])

    return model_pipeline
