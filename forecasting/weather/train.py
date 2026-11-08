
"""
Weather forecasting pipeline for KICaGEM.

- Loads weather measurements from PostgreSQL.
- Cleans implausible sensor values without modifying the database.
- Uses interval end timestamps as observation availability times.
- Evaluates Random Forest against a persistence baseline.
- Uses chronological train/validation/test splits.
- Handles wind direction with circular regression.
- Trains models in memory and discards them after forecasting.
- Saves evaluation results and forecasts as CSV files.
"""

from pathlib import Path
import sys
import math

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


# ==================================================
# 1. PROJECT PATHS AND DATABASE CONNECTION
# ==================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_conn, put_conn


BASE_DIR = Path(__file__).resolve().parent
RESULT_DIR = BASE_DIR / "results"

RESULT_DIR.mkdir(parents=True, exist_ok=True)


# ==================================================
# 2. CONFIGURATION
# ==================================================

FREQUENCY = "15min"
MINIMUM_SAMPLES = 2000

HORIZONS = {
    1: 15,
    2: 30,
    4: 60,
}

# lag_0 represents the latest available observation.
FEATURE_LAGS = [0, 1, 2, 4, 8, 96, 672]

ROLLING_WINDOWS = [4, 96, 672]

MODEL_PARAMETERS = {
    "n_estimators": 200,
    "max_depth": 15,
    "min_samples_leaf": 2,
    "random_state": 42,
    "n_jobs": -1,
}

WEATHER_VARIABLES = {
    "temperature": {
        "column": "temperature",
        "unit": "celsius",
    },
    "humidity": {
        "column": "humidity",
        "unit": "percent",
    },
    "barometric_pressure": {
        "column": "pressure",
        "unit": "hPa",
    },
    "wind_speed": {
        "column": "wind_speed",
        "unit": "m/s",
    },
    "rainfall": {
        "column": "rainfall_total",
        "unit": "mm",
    },
    "wind_direction": {
        "column": "wind_direction",
        "unit": "degree",
    },
}


# Plausibility limits.
# These are data-cleaning assumptions, not sensor specifications.
VALID_RANGES = {
    "temperature": (-40.0, 60.0),
    "humidity": (0.0, 100.0),
    "pressure": (850.0, 1100.0),
    "wind_speed": (0.0, 75.0),
    "rainfall_total": (0.0, 100.0),
    "wind_direction": (0.0, 360.0),
}


# ==================================================
# 3. LOAD WEATHER DATA
# ==================================================

SQL_QUERY = """
SELECT
    building,
    start,
    stop,
    temperature,
    humidity,
    pressure,
    wind_direction,
    wind_speed,
    rainfall_total
FROM public.weather_station
WHERE building IS NOT NULL
  AND start IS NOT NULL
  AND stop IS NOT NULL
ORDER BY building, stop;
"""


def load_weather_data():

    conn = get_conn()

    try:
        with conn.cursor() as cursor:
            cursor.execute(SQL_QUERY)
            rows = cursor.fetchall()

        columns = [
            "building",
            "start",
            "stop",
            "temperature",
            "humidity",
            "pressure",
            "wind_direction",
            "wind_speed",
            "rainfall_total",
        ]

        df = pd.DataFrame(rows, columns=columns)

        print(f"\nLoaded records: {len(df):,}")

        if df.empty:
            return df

        df["start"] = pd.to_datetime(
            df["start"],
            utc=True,
        )

        df["stop"] = pd.to_datetime(
            df["stop"],
            utc=True,
        )

        for column in WEATHER_VARIABLES.values():
            name = column["column"]

            df[name] = pd.to_numeric(
                df[name],
                errors="coerce",
            )

        return df

    finally:
        put_conn(conn)


# ==================================================
# 4. DATA QUALITY AND CLEANING
# ==================================================

def clean_weather_data(df):

    df = df.copy()

    print("\nDATA QUALITY CHECK")
    print("-" * 60)

    original_count = len(df)

    # Remove invalid intervals.
    valid_intervals = (
        df["stop"].notna()
        & df["start"].notna()
        & (df["stop"] > df["start"])
    )

    df = df.loc[valid_intervals].copy()

    print(
        "Invalid intervals removed:",
        original_count - len(df),
    )

    # Detect correlated sensor transmission errors.
    pressure_invalid = (
        (df["pressure"] < 850)
        | (df["pressure"] > 1100)
    )

    wind_invalid = (
        (df["wind_speed"] < 0)
        | (df["wind_speed"] > 75)
    )

    humidity_invalid = (
        (df["humidity"] < 0)
        | (df["humidity"] > 100)
    )

    rainfall_invalid = (
        (df["rainfall_total"] < 0)
        | (df["rainfall_total"] > 100)
    )

    direction_invalid = (
        (df["wind_direction"] < 0)
        | (df["wind_direction"] >= 360)
    )

    correlated_error = (
        pressure_invalid
        | wind_invalid
        | humidity_invalid
        | rainfall_invalid
        | direction_invalid
    )

    # Individual measurement cleaning.
    cleaning_rules = {
        "temperature": (
            (df["temperature"] < -40)
            | (df["temperature"] > 60)
        ),
        "humidity": humidity_invalid,
        "pressure": pressure_invalid,
        "wind_speed": wind_invalid,
        "rainfall_total": rainfall_invalid,
        "wind_direction": direction_invalid,
    }

    for column, invalid_mask in cleaning_rules.items():

        invalid_count = int(invalid_mask.sum())

        df.loc[invalid_mask, column] = np.nan

        print(
            f"{column}: {invalid_count} invalid values"
        )

    # -0.1 occurs as a repeated technical value
    # in records where other sensor channels also fail.
    # We only mask it when a correlated error is present.
    temperature_sentinel = (
        correlated_error
        & (df["temperature"] == -0.1)
    )

    direction_sentinel = (
        correlated_error
        & (df["wind_direction"] == -0.1)
    )

    df.loc[
        temperature_sentinel,
        "temperature",
    ] = np.nan

    df.loc[
        direction_sentinel,
        "wind_direction",
    ] = np.nan

    print(
        "Additional temperature sentinels:",
        int(temperature_sentinel.sum()),
    )

    print(
        "Additional wind direction sentinels:",
        int(direction_sentinel.sum()),
    )

    print(
        "Records with correlated sensor errors:",
        int(correlated_error.sum()),
    )

    print(
        "Remaining records:",
        len(df),
    )

    return df


# ==================================================
# 5. FEATURE ENGINEERING
# ==================================================

def add_time_features(df):

    index = df.index

    df["hour"] = index.hour
    df["day_of_week"] = index.day_of_week
    df["month"] = index.month

    df["is_weekend"] = (
        index.day_of_week >= 5
    ).astype(int)

    df["hour_sin"] = np.sin(
        2 * np.pi * index.hour / 24
    )

    df["hour_cos"] = np.cos(
        2 * np.pi * index.hour / 24
    )

    df["weekday_sin"] = np.sin(
        2 * np.pi * index.day_of_week / 7
    )

    df["weekday_cos"] = np.cos(
        2 * np.pi * index.day_of_week / 7
    )

    return df


def prepare_weather_series(building_df, variable):

    df = building_df.copy()

    # The interval end is the time at which
    # the complete measurement becomes available.
    df = df.sort_values("stop")
    df = df.set_index("stop")

    source_column = WEATHER_VARIABLES[variable]["column"]

    if variable == "wind_direction":

        radians = np.deg2rad(
            df[source_column]
        )

        df["_sin"] = np.sin(radians)
        df["_cos"] = np.cos(radians)

        df = df[["_sin", "_cos"]].resample(
            FREQUENCY
        ).mean()

        df["target_sin"] = df["_sin"]
        df["target_cos"] = df["_cos"]

    else:

        df = df[[source_column]].resample(
            FREQUENCY
        ).mean()

        df = df.rename(
            columns={
                source_column: "target"
            }
        )

    df = add_time_features(df)

    feature_columns = [
        "hour",
        "day_of_week",
        "month",
        "is_weekend",
        "hour_sin",
        "hour_cos",
        "weekday_sin",
        "weekday_cos",
    ]

    if variable == "wind_direction":

        source_columns = [
            "target_sin",
            "target_cos",
        ]

        for source in source_columns:

            for lag in FEATURE_LAGS:

                name = f"{source}_lag_{lag}"

                df[name] = df[source].shift(lag)

                feature_columns.append(name)

            for window in ROLLING_WINDOWS:

                name = f"{source}_rolling_{window}"

                df[name] = (
                    df[source]
                    .rolling(window)
                    .mean()
                )

                feature_columns.append(name)

    else:

        source = df["target"]

        for lag in FEATURE_LAGS:

            name = f"lag_{lag}"

            df[name] = source.shift(lag)

            feature_columns.append(name)

        for window in ROLLING_WINDOWS:

            name = f"rolling_mean_{window}"

            df[name] = (
                source
                .rolling(window)
                .mean()
            )

            feature_columns.append(name)

    return df, feature_columns


# ==================================================
# 6. MODEL AND METRIC HELPERS
# ==================================================

def create_model():

    return RandomForestRegressor(
        **MODEL_PARAMETERS
    )


def calculate_metrics(actual, predicted):

    actual = np.asarray(actual)
    predicted = np.asarray(predicted)

    mae = mean_absolute_error(
        actual,
        predicted,
    )

    rmse = math.sqrt(
        mean_squared_error(
            actual,
            predicted,
        )
    )

    return float(mae), float(rmse)


def circular_difference(actual, predicted):

    return (
        (predicted - actual + 180.0) % 360.0
    ) - 180.0


def angle_from_components(sin_values, cos_values):

    return (
        np.rad2deg(
            np.arctan2(
                sin_values,
                cos_values,
            )
        ) + 360.0
    ) % 360.0


def calculate_angle_metrics(actual, predicted):

    differences = circular_difference(
        np.asarray(actual),
        np.asarray(predicted),
    )

    mae = float(
        np.mean(np.abs(differences))
    )

    rmse = float(
        np.sqrt(np.mean(differences ** 2))
    )

    return mae, rmse


# ==================================================
# 7. HORIZON-SPECIFIC TRAINING AND FORECASTING
# ==================================================

def train_horizon(
    building,
    variable,
    df,
    feature_columns,
    steps,
    horizon_minutes,
):

    X = df[feature_columns]

    is_direction = (
        variable == "wind_direction"
    )

    if is_direction:

        y_sin = df["target_sin"].shift(-steps)
        y_cos = df["target_cos"].shift(-steps)

        target_valid = (
            y_sin.notna()
            & y_cos.notna()
        )

    else:

        y = df["target"].shift(-steps)
        target_valid = y.notna()

    valid = (
        X.notna().all(axis=1)
        & target_valid
    )

    X_valid = X.loc[valid]

    if is_direction:

        y_sin_valid = y_sin.loc[valid]
        y_cos_valid = y_cos.loc[valid]

    else:

        y_valid = y.loc[valid]

    n = len(X_valid)

    if n < MINIMUM_SAMPLES:
        print(f"Insufficient samples: {n}")
        return None, None

    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)

    X_train = X_valid.iloc[:train_end]
    X_val = X_valid.iloc[train_end:validation_end]
    X_test = X_valid.iloc[validation_end:]

    if is_direction:

        sin_train = y_sin_valid.iloc[:train_end]
        sin_val = y_sin_valid.iloc[train_end:validation_end]
        sin_test = y_sin_valid.iloc[validation_end:]

        cos_train = y_cos_valid.iloc[:train_end]
        cos_val = y_cos_valid.iloc[train_end:validation_end]
        cos_test = y_cos_valid.iloc[validation_end:]

    else:

        y_train = y_valid.iloc[:train_end]
        y_val = y_valid.iloc[train_end:validation_end]
        y_test = y_valid.iloc[validation_end:]

    if len(X_val) == 0 or len(X_test) == 0:
        return None, None

    # --------------------------------------------------
    # A. TRAIN RANDOM FOREST
    # --------------------------------------------------

    model = create_model()

    if is_direction:

        model.fit(X_train, sin_train)

        cos_model = create_model()
        cos_model.fit(X_train, cos_train)

        val_prediction = angle_from_components(
            model.predict(X_val),
            cos_model.predict(X_val),
        )

        val_actual = angle_from_components(
            sin_val,
            cos_val,
        )

        val_baseline = angle_from_components(
            df.loc[X_val.index, "target_sin"],
            df.loc[X_val.index, "target_cos"],
        )

        val_rf_mae, _ = calculate_angle_metrics(
            val_actual,
            val_prediction,
        )

        val_baseline_mae, _ = calculate_angle_metrics(
            val_actual,
            val_baseline,
        )

    else:

        model.fit(X_train, y_train)

        val_prediction = model.predict(X_val)

        val_actual = y_val.to_numpy()

        val_baseline = df.loc[
            X_val.index,
            "target",
        ].to_numpy()

        val_rf_mae, _ = calculate_metrics(
            val_actual,
            val_prediction,
        )

        val_baseline_mae, _ = calculate_metrics(
            val_actual,
            val_baseline,
        )

    # Select model using validation only.
    selected_model = (
        "random_forest"
        if val_rf_mae < val_baseline_mae
        else "persistence"
    )

    # --------------------------------------------------
    # B. TEST EVALUATION
    # --------------------------------------------------

    if is_direction:

        test_prediction = angle_from_components(
            model.predict(X_test),
            cos_model.predict(X_test),
        )

        test_actual = angle_from_components(
            sin_test,
            cos_test,
        )

        test_baseline = angle_from_components(
            df.loc[X_test.index, "target_sin"],
            df.loc[X_test.index, "target_cos"],
        )

        rf_test_mae, rf_test_rmse = calculate_angle_metrics(
            test_actual,
            test_prediction,
        )

        baseline_mae, baseline_rmse = calculate_angle_metrics(
            test_actual,
            test_baseline,
        )

    else:

        test_prediction = model.predict(X_test)

        test_actual = y_test.to_numpy()

        test_baseline = df.loc[
            X_test.index,
            "target",
        ].to_numpy()

        rf_test_mae, rf_test_rmse = calculate_metrics(
            test_actual,
            test_prediction,
        )

        baseline_mae, baseline_rmse = calculate_metrics(
            test_actual,
            test_baseline,
        )

    if selected_model == "random_forest":

        selected_mae = rf_test_mae
        selected_rmse = rf_test_rmse

    else:

        selected_mae = baseline_mae
        selected_rmse = baseline_rmse

    # --------------------------------------------------
    # C. LATEST AVAILABLE FORECAST ORIGIN
    # --------------------------------------------------

    latest_features = X.dropna().tail(1)

    if latest_features.empty:
        print("No valid latest features.")
        return None, None

    latest_timestamp = latest_features.index[-1]

    if is_direction:

        observed = float(
            angle_from_components(
                [df.loc[latest_timestamp, "target_sin"]],
                [df.loc[latest_timestamp, "target_cos"]],
            )[0]
        )

    else:

        observed = float(
            df.loc[latest_timestamp, "target"]
        )

    # --------------------------------------------------
    # D. FINAL MODEL TRAINING IN MEMORY
    # --------------------------------------------------

    # A final model is only required when Random Forest
    # performed better than the persistence baseline.
    # No model artifact is written to disk.

    if selected_model == "random_forest":

        final_model = create_model()

        if is_direction:

            final_model.fit(
                X_valid,
                y_sin_valid,
            )

            final_cos_model = create_model()

            final_cos_model.fit(
                X_valid,
                y_cos_valid,
            )

        else:

            final_model.fit(
                X_valid,
                y_valid,
            )

    # --------------------------------------------------
    # E. CREATE FORECAST
    # --------------------------------------------------

    if is_direction:

        if selected_model == "random_forest":

            predicted_sin = final_model.predict(
                latest_features
            )[0]

            predicted_cos = final_cos_model.predict(
                latest_features
            )[0]

            prediction = float(
                angle_from_components(
                    [predicted_sin],
                    [predicted_cos],
                )[0]
            )

        else:

            prediction = observed

    else:

        if selected_model == "random_forest":

            prediction = float(
                final_model.predict(
                    latest_features
                )[0]
            )

        else:

            prediction = observed

        # Physical output bounds.
        if variable == "humidity":
            prediction = float(np.clip(prediction, 0, 100))

        elif variable == "wind_speed":
            prediction = max(0.0, prediction)

        elif variable == "rainfall":
            prediction = max(0.0, prediction)

    evaluation = {
        "building": building,
        "sensor_type": variable,
        "horizon_minutes": horizon_minutes,
        "samples": n,
        "train_samples": len(X_train),
        "validation_samples": len(X_val),
        "test_samples": len(X_test),
        "validation_rf_mae": val_rf_mae,
        "validation_baseline_mae": val_baseline_mae,
        "selected_model": selected_model,
        "rf_test_mae": rf_test_mae,
        "mae": selected_mae,
        "rmse": selected_rmse,
        "baseline_mae": baseline_mae,
    }

    forecast = {
        "building": building,
        "sensor_type": variable,
        "forecast_origin": latest_timestamp,
        "forecast_timestamp": (
            latest_timestamp
            + pd.Timedelta(minutes=horizon_minutes)
        ),
        "horizon_minutes": horizon_minutes,
        "predicted_value": prediction,
        "unit": WEATHER_VARIABLES[variable]["unit"],
        "model_type": selected_model,
    }

    print(f"Validation RF MAE: {val_rf_mae:.5f}")
    print(f"Validation baseline MAE: {val_baseline_mae:.5f}")
    print(f"Selected model: {selected_model}")
    print(f"Test MAE: {selected_mae:.5f}")
    print(f"Test RMSE: {selected_rmse:.5f}")
    print(
        f"Forecast: {prediction:.5f} "
        f"{WEATHER_VARIABLES[variable]['unit']}"
    )

    return evaluation, forecast


# ==================================================
# 8. MAIN
# ==================================================

def main():

    print("\nWEATHER FORECASTING - KICaGEM")
    print("=" * 70)

    data = load_weather_data()

    if data.empty:
        print("No weather data found.")
        return

    data = clean_weather_data(data)

    all_evaluations = []
    all_forecasts = []

    buildings = data.groupby("building")

    print(
        f"\nWeather stations found: {len(buildings)}"
    )

    for building, building_df in buildings:

        print("\n" + "=" * 70)
        print(f"WEATHER STATION: {building}")
        print("=" * 70)

        for variable in WEATHER_VARIABLES:

            print(f"\nVariable: {variable}")

            df, feature_columns = prepare_weather_series(
                building_df,
                variable,
            )

            for steps, horizon_minutes in HORIZONS.items():

                print(
                    f"\n--- Horizon: {horizon_minutes} minutes ---"
                )

                evaluation, forecast = train_horizon(
                    building,
                    variable,
                    df,
                    feature_columns,
                    steps,
                    horizon_minutes,
                )

                if evaluation is not None:
                    all_evaluations.append(evaluation)

                if forecast is not None:
                    all_forecasts.append(forecast)

    evaluation_df = pd.DataFrame(
        all_evaluations
    )

    forecast_df = pd.DataFrame(
        all_forecasts
    )

    evaluation_path = (
        RESULT_DIR / "evaluation_results.csv"
    )

    forecast_path = (
        RESULT_DIR / "forecasts.csv"
    )

    evaluation_df.to_csv(
        evaluation_path,
        index=False,
    )

    forecast_df.to_csv(
        forecast_path,
        index=False,
    )

    print("\n" + "=" * 70)
    print("WEATHER TRAINING COMPLETED")
    print("=" * 70)

    print(
        f"Evaluation results: {len(evaluation_df)}"
    )

    print(
        f"Forecasts generated: {len(forecast_df)}"
    )

    print(
        f"\nEvaluation file: {evaluation_path}"
    )

    print(
        f"Forecast file: {forecast_path}"
    )


if __name__ == "__main__":
    main()
