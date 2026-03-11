"""Advanced Analytics Service — Baselines, anomaly detection, forecasting, confidence scoring.

Lightweight statistical engine using historical snapshots from SQLite.
No heavy ML dependencies — uses pure Python with basic linear regression.

TODO: Add LLM narrative layer for anomaly explanations
TODO: Add seasonal pattern detection
TODO: Add email/Slack anomaly alerts
"""

import math
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import get_connection

# ── Configuration (sensible defaults) ──
FORECAST_LOOKBACK_DAYS = 30
ANOMALY_THRESHOLD = 2.0  # Z-score threshold for anomaly flagging
REPORT_DEFAULT_PERIOD = 7
MIN_DATAPOINTS_FORECAST = 5
MIN_DATAPOINTS_BASELINE = 3


class AdvancedAnalyticsService:
    """Statistical analytics engine for marketing performance data."""

    # ══════════════════════════════════════════════════════════
    # BASELINES
    # ══════════════════════════════════════════════════════════

    def calculate_baseline(self, metric, days=30, platform=None):
        """Calculate statistical baseline for a metric using historical snapshots.

        Supported metrics: spend, ctr, cpa, conversions, clicks, impressions.
        """
        values = self._get_metric_series(metric, days, platform)

        if len(values) < MIN_DATAPOINTS_BASELINE:
            return {
                "metric": metric,
                "average": 0,
                "std_dev": 0,
                "min": 0,
                "max": 0,
                "datapoints": len(values),
                "confidence": "low",
                "period_days": days,
                "platform": platform,
                "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        avg = sum(values) / len(values)
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance)

        return {
            "metric": metric,
            "average": round(avg, 2),
            "std_dev": round(std_dev, 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "datapoints": len(values),
            "confidence": self._data_confidence(len(values), days),
            "period_days": days,
            "platform": platform,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def calculate_all_baselines(self, days=30, platform=None):
        """Calculate baselines for all key metrics."""
        metrics = ["spend", "conversions", "cpa", "ctr", "clicks", "impressions"]
        return {
            "baselines": {m: self.calculate_baseline(m, days, platform) for m in metrics},
            "period_days": days,
            "platform": platform,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ══════════════════════════════════════════════════════════
    # ANOMALY DETECTION
    # ══════════════════════════════════════════════════════════

    def detect_metric_anomalies(self, metric, days=7, platform=None):
        """Detect anomalies in recent data using Z-score deviation from baseline.

        Flags values that deviate more than ANOMALY_THRESHOLD standard deviations
        from the 30-day baseline.
        """
        baseline = self.calculate_baseline(metric, days=FORECAST_LOOKBACK_DAYS, platform=platform)
        avg = baseline["average"]
        std_dev = baseline["std_dev"]

        if baseline["datapoints"] < MIN_DATAPOINTS_BASELINE or std_dev == 0:
            return {
                "metric": metric,
                "anomalies": [],
                "baseline": baseline,
                "period_days": days,
                "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        recent = self._get_daily_metric_series(metric, days, platform)
        anomalies = []

        for entry in recent:
            value = entry["value"]
            z_score = (value - avg) / std_dev
            abs_z = abs(z_score)

            if abs_z >= ANOMALY_THRESHOLD:
                direction = "above" if z_score > 0 else "below"
                # Determine severity
                if abs_z >= ANOMALY_THRESHOLD * 2:
                    severity = "critical"
                elif abs_z >= ANOMALY_THRESHOLD * 1.5:
                    severity = "warning"
                else:
                    severity = "info"

                # Context-aware severity: CPA above baseline = bad, conversions below = bad
                is_negative = (metric in ("cpa", "spend") and direction == "above") or \
                              (metric in ("conversions", "ctr", "clicks") and direction == "below")

                anomalies.append({
                    "date": entry["date"],
                    "metric": metric,
                    "value": round(value, 2),
                    "baseline_avg": round(avg, 2),
                    "z_score": round(z_score, 2),
                    "deviation_pct": round((value - avg) / avg * 100, 1) if avg != 0 else 0,
                    "direction": direction,
                    "severity": severity,
                    "is_negative": is_negative,
                    "message": self._anomaly_message(metric, value, avg, direction, entry["date"]),
                })

        anomalies.sort(key=lambda a: abs(a["z_score"]), reverse=True)

        return {
            "metric": metric,
            "anomalies": anomalies,
            "baseline": baseline,
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def detect_all_anomalies(self, days=7, platform=None):
        """Run anomaly detection across all key metrics."""
        metrics = ["spend", "conversions", "cpa", "ctr"]
        all_anomalies = []
        for m in metrics:
            result = self.detect_metric_anomalies(m, days, platform)
            all_anomalies.extend(result["anomalies"])

        all_anomalies.sort(key=lambda a: abs(a["z_score"]), reverse=True)

        return {
            "anomalies": all_anomalies,
            "count": len(all_anomalies),
            "critical": sum(1 for a in all_anomalies if a["severity"] == "critical"),
            "warning": sum(1 for a in all_anomalies if a["severity"] == "warning"),
            "period_days": days,
            "platform": platform,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ══════════════════════════════════════════════════════════
    # FORECASTING
    # ══════════════════════════════════════════════════════════

    def forecast_metric(self, metric, horizon_days=7, platform=None):
        """Forecast a metric using linear regression on historical data.

        Returns predicted values, trend direction, and confidence level.
        """
        values = self._get_metric_series(metric, FORECAST_LOOKBACK_DAYS, platform)

        if len(values) < MIN_DATAPOINTS_FORECAST:
            return {
                "metric": metric,
                "forecast": [],
                "trend_direction": "insufficient_data",
                "confidence": "low",
                "slope": 0,
                "current_value": values[-1] if values else 0,
                "horizon_days": horizon_days,
                "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        # Linear regression: y = mx + b
        n = len(values)
        x = list(range(n))
        slope, intercept = self._linear_regression(x, values)

        # Generate forecast
        today = datetime.utcnow()
        forecast_points = []
        for i in range(1, horizon_days + 1):
            predicted = slope * (n + i - 1) + intercept
            predicted = max(0, predicted)  # No negative values for metrics
            forecast_date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
            forecast_points.append({
                "date": forecast_date,
                "predicted_value": round(predicted, 2),
                "day_offset": i,
            })

        # Trend direction
        if abs(slope) < 0.001:
            trend = "stable"
        elif slope > 0:
            trend = "rising"
        else:
            trend = "falling"

        # Context: for CPA, rising = bad; for conversions, rising = good
        if metric in ("cpa", "spend"):
            trend_sentiment = "negative" if trend == "rising" else ("positive" if trend == "falling" else "neutral")
        else:
            trend_sentiment = "positive" if trend == "rising" else ("negative" if trend == "falling" else "neutral")

        # R-squared for confidence
        r_squared = self._r_squared(x, values, slope, intercept)
        confidence = self._forecast_confidence(len(values), r_squared)

        current_value = values[-1] if values else 0
        forecast_end = forecast_points[-1]["predicted_value"] if forecast_points else current_value
        change_pct = round((forecast_end - current_value) / current_value * 100, 1) if current_value > 0 else 0

        return {
            "metric": metric,
            "forecast": forecast_points,
            "trend_direction": trend,
            "trend_sentiment": trend_sentiment,
            "confidence": confidence,
            "r_squared": round(r_squared, 3),
            "slope": round(slope, 4),
            "current_value": round(current_value, 2),
            "forecast_end_value": round(forecast_end, 2),
            "expected_change_pct": change_pct,
            "horizon_days": horizon_days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def forecast_all_metrics(self, horizon_days=7, platform=None):
        """Forecast all key metrics."""
        metrics = ["spend", "conversions", "cpa", "ctr"]
        return {
            "forecasts": {m: self.forecast_metric(m, horizon_days, platform) for m in metrics},
            "horizon_days": horizon_days,
            "platform": platform,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ══════════════════════════════════════════════════════════
    # CONFIDENCE SCORING
    # ══════════════════════════════════════════════════════════

    def compute_insight_confidence(self, data_points, consistency=None, sample_days=None):
        """Compute confidence level for any insight based on data quality.

        Args:
            data_points: number of data points used
            consistency: optional 0-1 value for historical consistency
            sample_days: optional number of days in sample
        """
        score = 0

        # Data volume
        if data_points >= 30:
            score += 40
        elif data_points >= 14:
            score += 30
        elif data_points >= 7:
            score += 20
        elif data_points >= 3:
            score += 10

        # Historical consistency (if provided)
        if consistency is not None:
            score += round(consistency * 30)
        else:
            score += 15  # neutral

        # Sample period
        if sample_days is not None:
            if sample_days >= 30:
                score += 30
            elif sample_days >= 14:
                score += 20
            elif sample_days >= 7:
                score += 10
        else:
            score += 15  # neutral

        if score >= 70:
            return "high"
        elif score >= 40:
            return "medium"
        return "low"

    # ══════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════

    def _get_metric_series(self, metric, days, platform=None):
        """Get daily metric values from snapshots."""
        conn = get_connection()
        try:
            since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            col = self._metric_col(metric)

            if platform:
                rows = conn.execute(
                    f"SELECT {col} as val FROM daily_snapshots WHERE date >= ? AND platform = ? ORDER BY date",
                    (since, platform),
                ).fetchall()
            else:
                # Aggregate across platforms per date
                rows = conn.execute(
                    f"SELECT SUM({col}) as val FROM daily_snapshots WHERE date >= ? GROUP BY date ORDER BY date",
                    (since,),
                ).fetchall()

            return [float(r["val"] or 0) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def _get_daily_metric_series(self, metric, days, platform=None):
        """Get daily metric values with dates."""
        conn = get_connection()
        try:
            since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            col = self._metric_col(metric)

            if platform:
                rows = conn.execute(
                    f"SELECT date, {col} as val FROM daily_snapshots WHERE date >= ? AND platform = ? ORDER BY date",
                    (since, platform),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT date, SUM({col}) as val FROM daily_snapshots WHERE date >= ? GROUP BY date ORDER BY date",
                    (since,),
                ).fetchall()

            return [{"date": r["date"], "value": float(r["val"] or 0)} for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    @staticmethod
    def _metric_col(metric):
        """Map metric name to safe column name."""
        valid = {"spend": "spend", "ctr": "ctr", "cpa": "cpa",
                 "conversions": "conversions", "clicks": "clicks",
                 "impressions": "impressions", "cpc": "cpc", "roas": "roas"}
        return valid.get(metric, "spend")

    @staticmethod
    def _linear_regression(x, y):
        """Simple least squares linear regression. Returns (slope, intercept)."""
        n = len(x)
        if n == 0:
            return 0, 0
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi ** 2 for xi in x)

        denom = n * sum_x2 - sum_x ** 2
        if denom == 0:
            return 0, sum_y / n if n > 0 else 0

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n
        return slope, intercept

    @staticmethod
    def _r_squared(x, y, slope, intercept):
        """Compute R-squared (coefficient of determination)."""
        n = len(y)
        if n == 0:
            return 0
        y_mean = sum(y) / n
        ss_tot = sum((yi - y_mean) ** 2 for yi in y)
        ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
        if ss_tot == 0:
            return 1.0 if ss_res == 0 else 0
        return max(0, 1 - ss_res / ss_tot)

    @staticmethod
    def _data_confidence(datapoints, period_days):
        """Determine confidence based on data volume."""
        if datapoints >= 21 and period_days >= 30:
            return "high"
        elif datapoints >= 7:
            return "medium"
        return "low"

    @staticmethod
    def _forecast_confidence(datapoints, r_squared):
        """Determine forecast confidence from data points and model fit."""
        if datapoints >= 21 and r_squared >= 0.6:
            return "high"
        elif datapoints >= 7 and r_squared >= 0.3:
            return "medium"
        return "low"

    @staticmethod
    def _anomaly_message(metric, value, baseline, direction, date):
        """Generate human-readable anomaly message."""
        metric_labels = {
            "spend": "Spend", "cpa": "CPA", "ctr": "CTR",
            "conversions": "Conversions", "clicks": "Clicks",
            "impressions": "Impressions",
        }
        label = metric_labels.get(metric, metric.title())
        if metric in ("spend", "cpa"):
            return f"{label} on {date} was ${value:.2f}, {direction} the baseline of ${baseline:.2f}"
        elif metric in ("ctr",):
            return f"{label} on {date} was {value:.2f}%, {direction} the baseline of {baseline:.2f}%"
        else:
            return f"{label} on {date} was {value:.0f}, {direction} the baseline of {baseline:.0f}"
