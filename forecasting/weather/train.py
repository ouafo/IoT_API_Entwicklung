
"""
Weather forecasting pipeline for KICaGEM.

- Loads weather measurements from PostgreSQL.
- Cleans implausible sensor values.
- Handles short sensor failures using sensor-specific imputation.
- Keeps original measurements separate from imputed features.
- Uses interval end timestamps as observation availability times.
- Evaluates Random Forest against a persistence baseline.
- Uses chronological train/validation/test splits.
- Handles wind direction with circular regression.
- Trains models in memory.
- Saves evaluation results and forecasts as CSV files.
- Protects existing forecasts against incomplete training runs.
"""

from pathlib import Path
import sys
import math
import os

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

# Maximum number of consecutive missing intervals
# that may be interpolated.
MAX_INTERPOLATION_GAP = 2

# Minimum proportion of available observations
# required for rolling features.
ROLLING_MINIMUM_RATIO = 0.8

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
# These are cleaning assumptions, not sensor specifications.
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

        df = pd.DataFrame(
            rows,
            columns=columns,
        )

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

        for config in WEATHER_VARIABLES.values():

            column = config["column"]

            df[column] = pd.to_numeric(
                df[column],
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
    print("-" * 70)

    original_count = len(df)

    # --------------------------------------------------
    # A. INVALID INTERVALS
    # --------------------------------------------------

    valid_intervals = (
        df["start"].notna()
        & df["stop"].notna()
        & (df["stop"] > df["start"])
    )

    df = df.loc[valid_intervals].copy()

    print(
        "Invalid intervals removed:",
        original_count - len(df),
    )

    # --------------------------------------------------
    # B. NON-FINITE VALUES
    # --------------------------------------------------

    for config in WEATHER_VARIABLES.values():

        column = config["column"]

        df[column] = df[column].replace(
            [np.inf, -np.inf],
            np.nan,
        )

    # --------------------------------------------------
    # C. PLAUSIBILITY CHECKS
    # --------------------------------------------------

    invalid_masks = {}

    for column, (minimum, maximum) in VALID_RANGES.items():

        invalid_mask = (
            (df[column] < minimum)
            | (df[column] > maximum)
        )

        invalid_masks[column] = invalid_mask.fillna(False)

    # Detect correlated sensor transmission errors.
    correlated_error = pd.Series(
        False,
        index=df.index,
    )

    for mask in invalid_masks.values():

        correlated_error |= mask

    # --------------------------------------------------
    # D. MASK INVALID SENSOR VALUES
    # --------------------------------------------------

    for column, invalid_mask in invalid_masks.items():

        invalid_count = int(
            invalid_mask.sum()
        )

        df.loc[
            invalid_mask,
            column,
        ] = np.nan

        print(
            f"{column}: {invalid_count} invalid values"
        )

    # --------------------------------------------------
    # E. TECHNICAL SENTINEL VALUES
    # --------------------------------------------------

    # -0.1 occurs as a technical value during
    # correlated transmission errors.

    temperature_sentinel = (
        correlated_error
        & (df["temperature"] == -0.1)
    )

    df.loc[
        temperature_sentinel,
        "temperature",
    ] = np.nan

    print(
        "Additional temperature sentinels:",
        int(temperature_sentinel.sum()),
    )

    # Normalize valid 360-degree measurements.
    df.loc[
        df["wind_direction"] == 360,
        "wind_direction",
    ] = 0.0

    # --------------------------------------------------
    # F. MISSING-VALUE REPORT
    # --------------------------------------------------

    print("\nMISSING VALUES AFTER CLEANING")

    for variable, config in WEATHER_VARIABLES.items():

        column = config["column"]

        missing = int(
            df[column].isna().sum()
        )

        print(
            f"{variable}: {missing} missing values"
        )

    print(
        "\nRecords with correlated sensor errors:",
        int(correlated_error.sum()),
    )

    print(
        "Remaining records:",
        len(df),
    )

    return df


# ==================================================
# 5. MISSING-VALUE IMPUTATION
# ==================================================

def interpolate_short_gaps(
    series,
    limit=MAX_INTERPOLATION_GAP,
):
    """
    Interpolate only internal gaps containing
    at most 'limit' consecutive missing intervals.

    Leading gaps, trailing gaps and longer outages
    remain NaN.

    The original measurement series is never modified.
    """

    series = series.copy()

    missing = series.isna()

    if not missing.any():
        return series

    # Identify consecutive missing-value groups.
    groups = (
        missing.ne(
            missing.shift(fill_value=False)
        ).cumsum()
    )

    gap_lengths = (
        missing.groupby(groups)
        .transform("sum")
    )

    # Only short gaps are eligible.
    eligible_missing = (
        missing
        & (gap_lengths <= limit)
    )

    interpolated = series.interpolate(
        method="time",
        limit_area="inside",
    )

    # Preserve long gaps and boundary gaps.
    result = series.copy()

    result.loc[eligible_missing] = (
        interpolated.loc[eligible_missing]
    )

    return result


def interpolate_wind_direction(series):
    """
    Circular interpolation of wind direction.

    Example:
    359 degrees -> missing -> 1 degree

    The interpolated value should be close to 0 degrees,
    not 180 degrees.
    """

    radians = np.deg2rad(series)

    sin_values = pd.Series(
        np.sin(radians),
        index=series.index,
    )

    cos_values = pd.Series(
        np.cos(radians),
        index=series.index,
    )

    sin_values = interpolate_short_gaps(
        sin_values
    )

    cos_values = interpolate_short_gaps(
        cos_values
    )

    magnitude = np.sqrt(
        sin_values ** 2 + cos_values ** 2
    )

    # Avoid unstable normalization.
    magnitude = magnitude.where(
        magnitude > 1e-8
    )

    sin_values = sin_values / magnitude
    cos_values = cos_values / magnitude

    return sin_values, cos_values


# ==================================================
# 6. FEATURE ENGINEERING
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


def get_rolling_min_periods(window):
    """
    Calculate the minimum number of valid observations
    required for a rolling feature.

    At least 80 percent of the window must be available.
    """

    return max(
        1,
        math.ceil(
            window * ROLLING_MINIMUM_RATIO
        ),
    )


def prepare_weather_series(
    building_df,
    variable,
):

    df = building_df.copy()

    # The interval end is the time at which
    # the complete measurement becomes available.
    df = df.sort_values("stop")
    df = df.set_index("stop")

    source_column = WEATHER_VARIABLES[variable]["column"]

    # --------------------------------------------------
    # A. RESAMPLING
    # --------------------------------------------------

    raw = df[source_column].resample(
        FREQUENCY
    ).mean()

    missing_before = int(
        raw.isna().sum()
    )

    # --------------------------------------------------
    # B. SENSOR-SPECIFIC IMPUTATION
    # --------------------------------------------------

    result = pd.DataFrame(
        index=raw.index
    )

    if variable == "wind_direction":

        # Original circular target components.
        radians = np.deg2rad(raw)

        target_sin = pd.Series(
            np.sin(radians),
            index=raw.index,
        )

        target_cos = pd.Series(
            np.cos(radians),
            index=raw.index,
        )

        # Interpolate only short gaps for features.
        feature_sin, feature_cos = (
            interpolate_wind_direction(raw)
        )

        result["target_sin"] = target_sin
        result["target_cos"] = target_cos

        result["feature_sin"] = feature_sin
        result["feature_cos"] = feature_cos

        missing_after = int(
            result["feature_sin"].isna().sum()
        )

    else:

        # Original observations remain untouched.
        result["target"] = raw

        # Imputed values are only used for features.
        result["feature_source"] = (
            interpolate_short_gaps(raw)
        )

        missing_after = int(
            result["feature_source"].isna().sum()
        )

    print(
        f"Missing values [{variable}]: "
        f"{missing_before} before, "
        f"{missing_after} after imputation"
    )

    # --------------------------------------------------
    # C. TIME FEATURES
    # --------------------------------------------------

    result = add_time_features(result)

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

    # --------------------------------------------------
    # D. LAG AND ROLLING FEATURES
    # --------------------------------------------------

    if variable == "wind_direction":

        for source in [
            "feature_sin",
            "feature_cos",
        ]:

            for lag in FEATURE_LAGS:

                name = f"{source}_lag_{lag}"

                result[name] = (
                    result[source].shift(lag)
                )

                feature_columns.append(name)

            for window in ROLLING_WINDOWS:

                name = f"{source}_rolling_{window}"

                min_periods = get_rolling_min_periods(
                    window
                )

                result[name] = (
                    result[source]
                    .rolling(
                        window,
                        min_periods=min_periods,
                    )
                    .mean()
                )

                feature_columns.append(name)

    else:

        source = result["feature_source"]

        for lag in FEATURE_LAGS:

            name = f"lag_{lag}"

            result[name] = (
                source.shift(lag)
            )

            feature_columns.append(name)

        for window in ROLLING_WINDOWS:

            name = f"rolling_mean_{window}"

            min_periods = get_rolling_min_periods(
                window
            )

            result[name] = (
                source
                .rolling(
                    window,
                    min_periods=min_periods,
                )
                .mean()
            )

            feature_columns.append(name)

    return result, feature_columns


# ==================================================
# 7. MODEL AND METRIC HELPERS
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


def angle_from_components(
    sin_values,
    cos_values,
):

    return (
        np.rad2deg(
            np.arctan2(
                sin_values,
                cos_values,
            )
        ) + 360.0
    ) % 360.0


def calculate_angle_metrics(
    actual,
    predicted,
):

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
# 8. HORIZON-SPECIFIC TRAINING AND FORECASTING
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

    # --------------------------------------------------
    # A. TARGET VALIDATION
    # --------------------------------------------------

    if is_direction:

        y_sin = df["target_sin"].shift(-steps)
        y_cos = df["target_cos"].shift(-steps)

        target_valid = (
            y_sin.notna()
            & y_cos.notna()
        )

        current_target_valid = (
            df["target_sin"].notna()
            & df["target_cos"].notna()
        )

    else:

        y = df["target"].shift(-steps)

        target_valid = y.notna()

        current_target_valid = (
            df["target"].notna()
        )

    # A row is valid only if:
    # 1. All features are available.
    # 2. The current observation is genuine.
    # 3. The future training target is genuine.

    valid = (
        X.notna().all(axis=1)
        & current_target_valid
        & target_valid
    )

    X_valid = X.loc[valid]

    if is_direction:

        y_sin_valid = y_sin.loc[valid]
        y_cos_valid = y_cos.loc[valid]

    else:

        y_valid = y.loc[valid]

    n = len(X_valid)

    print(
        f"Valid training samples: {n}"
    )

    if n < MINIMUM_SAMPLES:

        print(
            f"Insufficient samples: {n} "
            f"(minimum: {MINIMUM_SAMPLES})"
        )

        return None, None

    # --------------------------------------------------
    # B. CHRONOLOGICAL SPLIT
    # --------------------------------------------------

    train_end = int(n * 0.70)
    validation_end = int(n * 0.85)

    X_train = X_valid.iloc[:train_end]

    X_val = X_valid.iloc[
        train_end:validation_end
    ]

    X_test = X_valid.iloc[
        validation_end:
    ]

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

        print("Validation or test set is empty.")

        return None, None

    # --------------------------------------------------
    # C. TRAIN RANDOM FOREST
    # --------------------------------------------------

    model = create_model()

    if is_direction:

        model.fit(
            X_train,
            sin_train,
        )

        cos_model = create_model()

        cos_model.fit(
            X_train,
            cos_train,
        )

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

        model.fit(
            X_train,
            y_train,
        )

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
    # D. TEST EVALUATION
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

        rf_test_mae, rf_test_rmse = (
            calculate_angle_metrics(
                test_actual,
                test_prediction,
            )
        )

        baseline_mae, baseline_rmse = (
            calculate_angle_metrics(
                test_actual,
                test_baseline,
            )
        )

    else:

        test_prediction = model.predict(X_test)

        test_actual = y_test.to_numpy()

        test_baseline = df.loc[
            X_test.index,
            "target",
        ].to_numpy()

        rf_test_mae, rf_test_rmse = (
            calculate_metrics(
                test_actual,
                test_prediction,
            )
        )

        baseline_mae, baseline_rmse = (
            calculate_metrics(
                test_actual,
                test_baseline,
            )
        )

    if selected_model == "random_forest":

        selected_mae = rf_test_mae
        selected_rmse = rf_test_rmse

    else:

        selected_mae = baseline_mae
        selected_rmse = baseline_rmse

    # --------------------------------------------------
    # E. LATEST AVAILABLE FORECAST ORIGIN
    # --------------------------------------------------

    # Only genuine current measurements may define
    # the forecast origin.

    # First inspect the latest genuine observation,
    # even if some features are still missing.

    available_rows = X.loc[
        current_target_valid
    ]

    if not available_rows.empty:

        latest_observation = available_rows.index[-1]

        missing_features = (
            available_rows.loc[latest_observation]
            .index[
                available_rows.loc[latest_observation].isna()
            ]
            .tolist()
        )

        print(
            f"Latest genuine observation: "
            f"{latest_observation}"
        )

        print(
            f"Missing features at latest observation: "
            f"{missing_features}"
        )

    else:

        print(
            "No genuine current observations available."
        )

        return None, None

    # Only use a timestamp if every required feature
    # is available and the current target is genuine.

    latest_candidates = X.loc[
        current_target_valid
    ].dropna()

    if latest_candidates.empty:

        print("No valid latest forecast features.")

        return None, None

    latest_features = latest_candidates.tail(1)

    latest_timestamp = latest_features.index[-1]

    if is_direction:

        observed = float(
            angle_from_components(
                [
                    df.loc[
                        latest_timestamp,
                        "target_sin",
                    ]
                ],
                [
                    df.loc[
                        latest_timestamp,
                        "target_cos",
                    ]
                ],
            )[0]
        )

    else:

        observed = float(
            df.loc[
                latest_timestamp,
                "target",
            ]
        )

    # --------------------------------------------------
    # F. FINAL MODEL TRAINING
    # --------------------------------------------------

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
    # G. CREATE FORECAST
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

            prediction = float(
                np.clip(prediction, 0, 100)
            )

        elif variable in [
            "wind_speed",
            "rainfall",
        ]:

            prediction = max(
                0.0,
                prediction,
            )

        elif variable == "barometric_pressure":

            prediction = float(
                np.clip(prediction, 850, 1100)
            )

        elif variable == "temperature":

            prediction = float(
                np.clip(prediction, -40, 60)
            )

    # --------------------------------------------------
    # H. EVALUATION RESULT
    # --------------------------------------------------

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

    # --------------------------------------------------
    # I. FORECAST RESULT
    # --------------------------------------------------

    forecast = {
        "building": building,
        "sensor_type": variable,
        "forecast_origin": latest_timestamp,
        "forecast_timestamp": (
            latest_timestamp
            + pd.Timedelta(
                minutes=horizon_minutes
            )
        ),
        "horizon_minutes": horizon_minutes,
        "predicted_value": prediction,
        "unit": WEATHER_VARIABLES[variable]["unit"],
        "model_type": selected_model,
    }

    print(
        f"Validation RF MAE: {val_rf_mae:.5f}"
    )

    print(
        f"Validation baseline MAE: "
        f"{val_baseline_mae:.5f}"
    )

    print(
        f"Selected model: {selected_model}"
    )

    print(
        f"Test MAE: {selected_mae:.5f}"
    )

    print(
        f"Test RMSE: {selected_rmse:.5f}"
    )

    print(
        f"Forecast: {prediction:.5f} "
        f"{WEATHER_VARIABLES[variable]['unit']}"
    )

    print(
        f"Forecast origin: {latest_timestamp}"
    )

    return evaluation, forecast


# ==================================================
# 9. SAFE CSV WRITING
# ==================================================

def atomic_to_csv(df, path):
    """
    Write to a temporary file first.
    Replace the destination only after a successful write.
    """

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    df.to_csv(
        temporary_path,
        index=False,
    )

    os.replace(
        temporary_path,
        path,
    )


# ==================================================
# 10. MAIN
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

    building_ids = list(
        buildings.groups.keys()
    )

    print(
        f"\nWeather stations found: {len(building_ids)}"
    )

    # --------------------------------------------------
    # A. TRAIN ALL BUILDINGS AND SENSORS
    # --------------------------------------------------

    for building, building_df in buildings:

        print("\n" + "=" * 70)
        print(f"WEATHER STATION: {building}")
        print("=" * 70)

        for variable in WEATHER_VARIABLES:

            print(f"\nVariable: {variable}")

            df, feature_columns = (
                prepare_weather_series(
                    building_df,
                    variable,
                )
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

                    all_evaluations.append(
                        evaluation
                    )

                if forecast is not None:

                    all_forecasts.append(
                        forecast
                    )

    # --------------------------------------------------
    # B. CREATE RESULT DATAFRAMES
    # --------------------------------------------------

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

    diagnostics_path = (
        RESULT_DIR / "forecast_generation_diagnostics.csv"
    )

    # Evaluation results are saved independently.
    if not evaluation_df.empty:

        atomic_to_csv(
            evaluation_df,
            evaluation_path,
        )

    # --------------------------------------------------
    # C. CHECK FORECAST COMPLETENESS
    # --------------------------------------------------

    expected_forecasts = {
        (building, variable, horizon)
        for building in building_ids
        for variable in WEATHER_VARIABLES
        for horizon in HORIZONS.values()
    }

    generated_forecasts = {
        (
            row["building"],
            row["sensor_type"],
            row["horizon_minutes"],
        )
        for row in all_forecasts
    }

    missing_forecasts = (
        expected_forecasts - generated_forecasts
    )

    extra_forecasts = (
        generated_forecasts - expected_forecasts
    )

    print("\n" + "=" * 70)
    print("FORECAST COMPLETENESS CHECK")
    print("=" * 70)

    print(
        f"Expected forecasts: {len(expected_forecasts)}"
    )

    print(
        f"Generated forecasts: {len(generated_forecasts)}"
    )

    print(
        f"Missing forecasts: {len(missing_forecasts)}"
    )

    # --------------------------------------------------
    # D. PUBLISH ONLY COMPLETE FORECAST RESULTS
    # --------------------------------------------------

    if (
        not missing_forecasts
        and not extra_forecasts
        and not forecast_df.empty
    ):

        atomic_to_csv(
            forecast_df,
            forecast_path,
        )

        print(
            "\nAll expected forecasts generated successfully."
        )

        print(
            f"Forecast file updated: {forecast_path}"
        )

        if diagnostics_path.exists():

            diagnostics_path.unlink()

    else:

        diagnostic_rows = [
            {
                "building": building,
                "sensor_type": variable,
                "horizon_minutes": horizon,
                "status": "missing",
            }
            for building, variable, horizon
            in sorted(missing_forecasts)
        ]

        diagnostics_df = pd.DataFrame(
            diagnostic_rows,
            columns=[
                "building",
                "sensor_type",
                "horizon_minutes",
                "status",
            ],
        )

        atomic_to_csv(
            diagnostics_df,
            diagnostics_path,
        )

        print(
            "\nWARNING: Forecast generation incomplete."
        )

        print(
            "The existing forecasts.csv was NOT overwritten."
        )

        print(
            f"Diagnostics: {diagnostics_path}"
        )

        for row in diagnostic_rows:

            print(
                f"Missing: {row['building']} / "
                f"{row['sensor_type']} / "
                f"{row['horizon_minutes']} min"
            )

    # --------------------------------------------------
    # E. FINAL SUMMARY
    # --------------------------------------------------

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
        f"Evaluation file: {evaluation_path}"
    )

    print(
        f"Forecast file: {forecast_path}"
    )


if __name__ == "__main__":

    main()
