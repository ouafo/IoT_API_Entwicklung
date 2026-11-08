
"""
Room climate forecasting.

Training data is loaded directly from PostgreSQL.
Forecast results are written to CSV for compatibility with the existing API.

Forecast targets:
- temperature
- humidity
- co2
- light_mean

Motion is intentionally excluded from regression.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from psycopg.rows import dict_row

from app.database.connection import get_conn, put_conn


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
RESULT_DIR = BASE_DIR / "forecasting" / "room_climate" / "results"

FORECAST_FILE = RESULT_DIR / "forecasts.csv"
EVALUATION_FILE = RESULT_DIR / "evaluation_results.csv"
QUALITY_FILE = RESULT_DIR / "data_quality.csv"
SUMMARY_FILE = RESULT_DIR / "summary.json"

FREQUENCY = "15min"
HORIZONS = [1, 2, 3, 4]

# Minimum number of usable training observations per room and sensor.
MIN_SAMPLES = 500

# Data quality thresholds.
MIN_COMPLETENESS = 70.0
MAX_DATA_AGE_MINUTES = 60

# Historical features.
LAGS = [0, 1, 2, 4, 8, 96, 672]
ROLLING_WINDOWS = [4, 96]

MODEL_PARAMETERS = {
    "n_estimators": 200,
    "max_depth": 15,
    "min_samples_leaf": 2,
    "random_state": 42,
    "n_jobs": -1,
}

SENSORS = {
    "temperature": {
        "column": "temperature",
        "unit_column": "temperature_unit",
        "unit_default": "°C",
        "minimum": -10,
        "maximum": 50,
    },
    "humidity": {
        "column": "humidity",
        "unit_column": "humidity_unit",
        "unit_default": "%",
        "minimum": 0,
        "maximum": 100,
    },
    "co2": {
        "column": "co2",
        "unit_column": "co2_unit",
        "unit_default": "ppm",
        "minimum": 250,
        "maximum": 5000,
    },
    "light": {
        "column": "light_mean",
        "unit_column": "light_unit",
        "unit_default": "Lux",
        "minimum": 0,
        "maximum": 100000,
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------

def load_data_from_database() -> pd.DataFrame:
    """
    Load room climate measurements directly from PostgreSQL.
    No input CSV is required.
    """

    query = """
        SELECT
            building,
            room_location,
            start,
            temperature,
            humidity,
            co2,
            light_mean,
            temperature_unit,
            humidity_unit,
            co2_unit,
            light_unit
        FROM public.room_climate
        WHERE start IS NOT NULL
        ORDER BY building, room_location, start;
    """

    conn = get_conn()

    try:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        df = pd.DataFrame(rows)

    finally:
        put_conn(conn)

    if df.empty:
        raise RuntimeError(
            "Die Datenbanktabelle public.room_climate enthält keine Messwerte."
        )

    df["start"] = pd.to_datetime(df["start"], utc=True, errors="coerce")

    df = df.dropna(
        subset=["start", "building", "room_location"]
    )

    df["building"] = df["building"].astype(str)
    df["room_location"] = df["room_location"].astype(str)

    for sensor in SENSORS:
        column = SENSORS[sensor]["column"]
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["room_id"] = (
        df["building"] + "-" + df["room_location"]
    )

    df = df.sort_values(
        ["room_id", "start"]
    ).reset_index(drop=True)

    logger.info(
        "Datenbank erfolgreich geladen: %s Messdatensätze, %s Räume",
        len(df),
        df["room_id"].nunique(),
    )

    return df


# ---------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------

def clean_sensor_values(
    series: pd.Series,
    sensor_type: str,
) -> pd.Series:
    """
    Remove physically implausible values and sensor error values.

    Missing values remain missing. Targets are never artificially
    interpolated.
    """

    config = SENSORS[sensor_type]

    cleaned = pd.to_numeric(
        series,
        errors="coerce",
    ).astype(float)

    cleaned = cleaned.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    cleaned = cleaned.where(
        (cleaned >= config["minimum"])
        & (cleaned <= config["maximum"])
    )

    return cleaned


def get_sensor_unit(
    room_df: pd.DataFrame,
    sensor_type: str,
) -> str:
    """Determine the unit from the database."""

    unit_column = SENSORS[sensor_type]["unit_column"]

    if unit_column in room_df.columns:
        values = room_df[unit_column].dropna()

        if not values.empty:
            unit = str(values.iloc[0]).strip()

            normalized = {
                "celsius": "°C",
                "percent": "%",
                "ppm": "ppm",
                "Lux": "Lux",
            }

            return normalized.get(unit, unit)

    return SENSORS[sensor_type]["unit_default"]


def prepare_room_series(
    room_df: pd.DataFrame,
    sensor_type: str,
) -> pd.Series:
    """
    Create a regular 15-minute time series for one room and sensor.

    Duplicate timestamps are aggregated using the median.
    Missing intervals remain NaN.
    """

    column = SENSORS[sensor_type]["column"]

    data = room_df[["start", column]].copy()

    data[column] = clean_sensor_values(
        data[column],
        sensor_type,
    )

    data = data.dropna(subset=["start"])

    # Multiple measurements for the same timestamp:
    # use the median instead of arbitrarily selecting one.
    series = (
        data.groupby("start")[column]
        .median()
        .sort_index()
    )

    if series.empty:
        return series

    # Regular 15-minute time grid.
    series = series.resample(FREQUENCY).median()

    return series.astype(float)


# ---------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------

def evaluate_data_quality(
    room_series: dict[tuple[str, str], pd.Series],
    latest_database_timestamp: pd.Timestamp,
) -> tuple[dict[tuple[str, str], bool], list[dict[str, Any]]]:

    eligibility = {}
    quality_results = []

    for (room_id, sensor_type), series in room_series.items():

        if series.empty:
            continue

        valid = series.dropna()

        if valid.empty:
            completeness = 0.0
            latest_age_minutes = float("inf")
        else:
            completeness = (
                valid.notna().sum() / len(series) * 100
            )

            latest_age_minutes = (
                latest_database_timestamp - valid.index.max()
            ).total_seconds() / 60

        eligible = (
            len(valid) >= MIN_SAMPLES
            and completeness >= MIN_COMPLETENESS
            and latest_age_minutes <= MAX_DATA_AGE_MINUTES
        )

        eligibility[(room_id, sensor_type)] = eligible

        quality_results.append({
            "room_id": room_id,
            "sensor_type": sensor_type,
            "valid_samples": len(valid),
            "total_intervals": len(series),
            "completeness_percent": round(completeness, 2),
            "latest_data_age_minutes": round(
                latest_age_minutes, 2
            ),
            "eligible": eligible,
        })

    return eligibility, quality_results


# ---------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------

def create_features(series: pd.Series) -> pd.DataFrame:
    """
    Create lag, rolling and calendar features.

    Only historical/current measurements are used.
    """

    features = pd.DataFrame(index=series.index)

    for lag in LAGS:
        features[f"lag_{lag}"] = series.shift(lag)

    for window in ROLLING_WINDOWS:
        features[f"rolling_mean_{window}"] = (
            series.rolling(
                window=window,
                min_periods=window,
            ).mean()
        )

    hour = series.index.hour
    weekday = series.index.dayofweek

    features["hour_sin"] = np.sin(
        2 * np.pi * hour / 24
    )

    features["hour_cos"] = np.cos(
        2 * np.pi * hour / 24
    )

    features["weekday_sin"] = np.sin(
        2 * np.pi * weekday / 7
    )

    features["weekday_cos"] = np.cos(
        2 * np.pi * weekday / 7
    )

    return features


# ---------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------

def calculate_metrics(
    actual: pd.Series,
    predicted: np.ndarray,
) -> dict[str, float]:

    return {
        "mae": float(
            mean_absolute_error(actual, predicted)
        ),
        "rmse": float(
            np.sqrt(mean_squared_error(actual, predicted))
        ),
    }


def train_sensor_model(
    room_id: str,
    sensor_type: str,
    series: pd.Series,
    unit: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:

    forecasts = []
    evaluations = []

    # Fill only short gaps in historical feature values.
    # Original target values remain unchanged.
    feature_series = series.ffill(limit=2)

    features = create_features(feature_series)

    for horizon in HORIZONS:

        target = series.shift(-horizon)

        dataset = features.copy()
        dataset["target"] = target

        dataset = dataset.replace(
            [np.inf, -np.inf],
            np.nan,
        ).dropna()

        if len(dataset) < MIN_SAMPLES:
            logger.info(
                "Zu wenige Trainingsdaten: Raum=%s Sensor=%s Horizont=%s",
                room_id,
                sensor_type,
                horizon,
            )
            continue

        X = dataset.drop(columns=["target"])
        y = dataset["target"]

        # Chronological split: 70% / 15% / 15%.
        n = len(dataset)

        train_end = int(n * 0.70)
        validation_end = int(n * 0.85)

        X_train = X.iloc[:train_end]
        y_train = y.iloc[:train_end]

        X_validation = X.iloc[train_end:validation_end]
        y_validation = y.iloc[train_end:validation_end]

        X_test = X.iloc[validation_end:]
        y_test = y.iloc[validation_end:]

        if (
            len(X_train) == 0
            or len(X_validation) == 0
            or len(X_test) == 0
        ):
            continue

        # Random Forest.
        model = RandomForestRegressor(
            **MODEL_PARAMETERS
        )

        model.fit(X_train, y_train)

        validation_prediction = model.predict(
            X_validation
        )

        rf_validation_mae = mean_absolute_error(
            y_validation,
            validation_prediction,
        )

        # Persistence baseline:
        # future value = latest observed value.
        persistence_validation = X_validation["lag_0"].to_numpy()

        persistence_validation_mae = mean_absolute_error(
            y_validation,
            persistence_validation,
        )

        # Select the better model using validation data only.
        use_random_forest = (
            rf_validation_mae < persistence_validation_mae
        )

        if use_random_forest:
            test_prediction = model.predict(X_test)
            model_type = "RandomForest"
        else:
            test_prediction = X_test["lag_0"].to_numpy()
            model_type = "Persistence"

        metrics = calculate_metrics(
            y_test,
            test_prediction,
        )

        evaluations.append({
            "room_id": room_id,
            "sensor_type": sensor_type,
            "horizon_minutes": horizon * 15,
            "model_type": model_type,
            "sample_count": len(dataset),
            "validation_mae_random_forest": float(
                rf_validation_mae
            ),
            "validation_mae_persistence": float(
                persistence_validation_mae
            ),
            "test_mae": metrics["mae"],
            "test_rmse": metrics["rmse"],
        })

        # Find the latest usable feature row for forecasting.
        latest_features = features.dropna()

        if latest_features.empty:
            continue

        latest_row = latest_features.iloc[[-1]]
        forecast_origin = latest_row.index[0]

        # Fit the selected model using all available historical
        # training examples.
        if use_random_forest:
            final_model = RandomForestRegressor(
                **MODEL_PARAMETERS
            )

            final_model.fit(X, y)

            predicted_value = float(
                final_model.predict(latest_row)[0]
            )
        else:
            predicted_value = float(
                latest_row["lag_0"].iloc[0]
            )

        # Forecast timestamp is based on the actual forecast origin.
        forecast_timestamp = (
            forecast_origin
            + pd.Timedelta(minutes=horizon * 15)
        )

        # Keep predicted_temperature_c for compatibility with
        # the existing temperature API. Non-temperature records
        # will be handled in the upcoming service update.
        predicted_temperature = (
            predicted_value
            if sensor_type == "temperature"
            else np.nan
        )

        forecasts.append({
            "room_id": room_id,
            "sensor_type": sensor_type,
            "forecast_origin": forecast_origin,
            "forecast_timestamp": forecast_timestamp,
            "horizon_minutes": horizon * 15,
            "predicted_value": predicted_value,
            "unit": unit,
            "predicted_temperature_c": predicted_temperature,
            "model_type": model_type,
        })

    return forecasts, evaluations


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger.info("Starte Raumklima-Prognose.")

    # 1. Load PostgreSQL data.
    df = load_data_from_database()

    latest_database_timestamp = df["start"].max()

    all_room_series = {}
    all_room_units = {}

    # 2. Prepare time series per room and sensor.
    for room_id, room_df in df.groupby("room_id"):

        for sensor_type in SENSORS:

            series = prepare_room_series(
                room_df,
                sensor_type,
            )

            if series.empty:
                continue

            all_room_series[(room_id, sensor_type)] = series

            all_room_units[(room_id, sensor_type)] = (
                get_sensor_unit(room_df, sensor_type)
            )

    # 3. Evaluate data quality.
    eligibility, quality_results = evaluate_data_quality(
        all_room_series,
        latest_database_timestamp,
    )

    pd.DataFrame(quality_results).to_csv(
        QUALITY_FILE,
        index=False,
    )

    # 4. Train models.
    all_forecasts = []
    all_evaluations = []

    for (room_id, sensor_type), series in all_room_series.items():

        if not eligibility.get((room_id, sensor_type), False):
            logger.info(
                "Übersprungen: Raum=%s Sensor=%s",
                room_id,
                sensor_type,
            )
            continue

        unit = all_room_units[(room_id, sensor_type)]

        logger.info(
            "Trainiere: Raum=%s Sensor=%s",
            room_id,
            sensor_type,
        )

        forecasts, evaluations = train_sensor_model(
            room_id=room_id,
            sensor_type=sensor_type,
            series=series,
            unit=unit,
        )

        all_forecasts.extend(forecasts)
        all_evaluations.extend(evaluations)

    # 5. Save results.
    forecast_columns = [
        "room_id",
        "sensor_type",
        "forecast_origin",
        "forecast_timestamp",
        "horizon_minutes",
        "predicted_value",
        "unit",
        "predicted_temperature_c",
        "model_type",
    ]

    evaluation_columns = [
        "room_id",
        "sensor_type",
        "horizon_minutes",
        "model_type",
        "sample_count",
        "validation_mae_random_forest",
        "validation_mae_persistence",
        "test_mae",
        "test_rmse",
    ]

    forecasts_df = pd.DataFrame(
        all_forecasts,
        columns=forecast_columns,
    )

    evaluations_df = pd.DataFrame(
        all_evaluations,
        columns=evaluation_columns,
    )

    forecasts_df.to_csv(
        FORECAST_FILE,
        index=False,
    )

    evaluations_df.to_csv(
        EVALUATION_FILE,
        index=False,
    )

    summary = {
        "database_table": "public.room_climate",
        "input_csv_used": False,
        "training_timestamp": pd.Timestamp.now(
            tz="UTC"
        ).isoformat(),
        "rooms_processed": int(
            forecasts_df["room_id"].nunique()
        ) if not forecasts_df.empty else 0,
        "sensors_processed": (
            sorted(forecasts_df["sensor_type"].unique().tolist())
            if not forecasts_df.empty
            else []
        ),
        "forecast_count": len(forecasts_df),
        "evaluation_count": len(evaluations_df),
        "horizons_minutes": [
            horizon * 15 for horizon in HORIZONS
        ],
    }

    SUMMARY_FILE.write_text(
        json.dumps(
            summary,
            indent=4,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    logger.info(
        "Training abgeschlossen. Forecasts: %s",
        len(forecasts_df),
    )

    logger.info(
        "Ergebnisse gespeichert unter: %s",
        RESULT_DIR,
    )


if __name__ == "__main__":
    main()
