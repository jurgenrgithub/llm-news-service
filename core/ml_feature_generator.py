"""Generate ML-ready features from weekly intelligence."""

import json
from typing import Dict, List
from core.database import get_cursor

# Sentiment string to numeric mapping
SENTIMENT_MAP = {
    'positive': 0.75,
    'neutral': 0.5,
    'negative': 0.25,
    'mixed': 0.5,
    None: 0.5
}

# Signal strength to numeric mapping
SIGNAL_MAP = {
    'strong': 1.0,
    'moderate': 0.66,
    'weak': 0.33,
    'none': 0.0,
    None: 0.0
}

# Dimension code to column prefix mapping
DIMENSION_PREFIX_MAP = {
    'injury_status': 'injury',
    'fitness_health': 'fitness',
    'selection_security': 'selection',
    'role_change': 'role',
    'form_trajectory': 'form',
    'captaincy_potential': 'captaincy',
    'load_management': 'load',
    'coaching_sentiment': 'coaching'
}

DIMENSION_CODES = list(DIMENSION_PREFIX_MAP.keys())


class MLFeatureGenerator:
    """Generates flattened ML features from weekly intelligence."""

    def generate_for_round(self, round_id: int) -> Dict:
        """Generate ML features for all entities in a round."""
        results = {"generated": 0, "errors": []}

        with get_cursor() as cursor:
            # Get all entities with verdicts for this round
            cursor.execute("""
                SELECT DISTINCT entity_id FROM weekly_verdicts WHERE round_id = %s
            """, (round_id,))
            entity_ids = [row["entity_id"] for row in cursor.fetchall()]

        for entity_id in entity_ids:
            try:
                if self._generate_entity_features(entity_id, round_id):
                    results["generated"] += 1
            except Exception as e:
                results["errors"].append(f"{entity_id}: {e}")

        # Refresh materialized view
        try:
            with get_cursor() as cursor:
                cursor.execute("REFRESH MATERIALIZED VIEW ml_feature_export")
        except Exception as e:
            results["errors"].append(f"Materialized view refresh: {e}")

        return results

    def _generate_entity_features(self, entity_id: str, round_id: int) -> bool:
        """Generate ML features for a single entity-round."""
        features = {
            # Initialize all dimension features to defaults
            'injury_mentioned': False, 'injury_sentiment': None, 'injury_signal': None,
            'fitness_mentioned': False, 'fitness_sentiment': None, 'fitness_signal': None,
            'selection_mentioned': False, 'selection_sentiment': None, 'selection_signal': None,
            'role_mentioned': False, 'role_sentiment': None, 'role_signal': None,
            'form_mentioned': False, 'form_sentiment': None, 'form_signal': None,
            'captaincy_mentioned': False, 'captaincy_sentiment': None, 'captaincy_signal': None,
            'load_mentioned': False, 'load_sentiment': None, 'load_signal': None,
            'coaching_mentioned': False, 'coaching_sentiment': None, 'coaching_signal': None,
        }
        total_articles = 0
        sentiment_sum = 0.0
        signal_sum = 0.0
        dim_count = 0

        with get_cursor() as cursor:
            # Get dimension snapshots
            cursor.execute("""
                SELECT d.code, ws.sentiment, ws.signal_strength, ws.article_count,
                       ws.ml_features
                FROM weekly_snapshots ws
                JOIN dimensions d ON ws.dimension_id = d.id
                WHERE ws.entity_id = %s AND ws.round_id = %s
            """, (entity_id, round_id))
            snapshots = cursor.fetchall()

            # Get verdict
            cursor.execute("""
                SELECT captain_rating, risk_level, trade_signal, verdict_features,
                       confidence
                FROM weekly_verdicts
                WHERE entity_id = %s AND round_id = %s
            """, (entity_id, round_id))
            verdict = cursor.fetchone()

        if not verdict:
            return False

        # Process dimension snapshots
        for snap in snapshots:
            code = snap["code"]
            prefix = DIMENSION_PREFIX_MAP.get(code)
            if not prefix:
                continue

            article_count = snap["article_count"] or 0
            features[f"{prefix}_mentioned"] = article_count > 0
            features[f"{prefix}_sentiment"] = SENTIMENT_MAP.get(snap["sentiment"], 0.5)
            features[f"{prefix}_signal"] = SIGNAL_MAP.get(snap["signal_strength"], 0.0)

            total_articles += article_count
            if snap["sentiment"]:
                sentiment_sum += SENTIMENT_MAP.get(snap["sentiment"], 0.5)
                dim_count += 1
            signal_sum += SIGNAL_MAP.get(snap["signal_strength"], 0.0)

        # Extract verdict features
        verdict_features = verdict["verdict_features"]
        if isinstance(verdict_features, str):
            verdict_features = json.loads(verdict_features)
        vf = verdict_features or {}

        features["captain_rating"] = verdict["captain_rating"]
        features["risk_level"] = verdict["risk_level"]
        features["trade_signal"] = verdict["trade_signal"]
        features["injury_risk_score"] = vf.get("injury_risk", 0.5)
        features["form_score"] = vf.get("form_score", 0.5)
        features["selection_certainty"] = vf.get("selection_certainty", 0.5)
        features["upside_potential"] = vf.get("upside_potential", 0.5)
        features["floor_safety"] = vf.get("floor_safety", 0.5)

        # Aggregates
        features["total_article_count"] = total_articles
        features["overall_sentiment"] = sentiment_sum / dim_count if dim_count > 0 else 0.5
        features["overall_signal_strength"] = signal_sum / len(DIMENSION_CODES) if DIMENSION_CODES else 0.0
        features["confidence"] = float(verdict["confidence"]) if verdict["confidence"] else 0.5

        # Upsert to database
        self._upsert_features(entity_id, round_id, features)
        return True

    def _upsert_features(self, entity_id: str, round_id: int, features: Dict):
        """Insert or update ML features."""
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO ml_weekly_features (
                    entity_id, round_id,
                    injury_mentioned, injury_sentiment, injury_signal,
                    fitness_mentioned, fitness_sentiment, fitness_signal,
                    selection_mentioned, selection_sentiment, selection_signal,
                    role_mentioned, role_sentiment, role_signal,
                    form_mentioned, form_sentiment, form_signal,
                    captaincy_mentioned, captaincy_sentiment, captaincy_signal,
                    load_mentioned, load_sentiment, load_signal,
                    coaching_mentioned, coaching_sentiment, coaching_signal,
                    captain_rating, risk_level, trade_signal,
                    injury_risk_score, form_score, selection_certainty,
                    upside_potential, floor_safety,
                    total_article_count, overall_sentiment, overall_signal_strength,
                    confidence
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (entity_id, round_id) DO UPDATE SET
                    injury_mentioned = EXCLUDED.injury_mentioned,
                    injury_sentiment = EXCLUDED.injury_sentiment,
                    injury_signal = EXCLUDED.injury_signal,
                    fitness_mentioned = EXCLUDED.fitness_mentioned,
                    fitness_sentiment = EXCLUDED.fitness_sentiment,
                    fitness_signal = EXCLUDED.fitness_signal,
                    selection_mentioned = EXCLUDED.selection_mentioned,
                    selection_sentiment = EXCLUDED.selection_sentiment,
                    selection_signal = EXCLUDED.selection_signal,
                    role_mentioned = EXCLUDED.role_mentioned,
                    role_sentiment = EXCLUDED.role_sentiment,
                    role_signal = EXCLUDED.role_signal,
                    form_mentioned = EXCLUDED.form_mentioned,
                    form_sentiment = EXCLUDED.form_sentiment,
                    form_signal = EXCLUDED.form_signal,
                    captaincy_mentioned = EXCLUDED.captaincy_mentioned,
                    captaincy_sentiment = EXCLUDED.captaincy_sentiment,
                    captaincy_signal = EXCLUDED.captaincy_signal,
                    load_mentioned = EXCLUDED.load_mentioned,
                    load_sentiment = EXCLUDED.load_sentiment,
                    load_signal = EXCLUDED.load_signal,
                    coaching_mentioned = EXCLUDED.coaching_mentioned,
                    coaching_sentiment = EXCLUDED.coaching_sentiment,
                    coaching_signal = EXCLUDED.coaching_signal,
                    captain_rating = EXCLUDED.captain_rating,
                    risk_level = EXCLUDED.risk_level,
                    trade_signal = EXCLUDED.trade_signal,
                    injury_risk_score = EXCLUDED.injury_risk_score,
                    form_score = EXCLUDED.form_score,
                    selection_certainty = EXCLUDED.selection_certainty,
                    upside_potential = EXCLUDED.upside_potential,
                    floor_safety = EXCLUDED.floor_safety,
                    total_article_count = EXCLUDED.total_article_count,
                    overall_sentiment = EXCLUDED.overall_sentiment,
                    overall_signal_strength = EXCLUDED.overall_signal_strength,
                    confidence = EXCLUDED.confidence,
                    generated_at = NOW()
            """, (
                entity_id, round_id,
                features.get("injury_mentioned", False),
                features.get("injury_sentiment"),
                features.get("injury_signal"),
                features.get("fitness_mentioned", False),
                features.get("fitness_sentiment"),
                features.get("fitness_signal"),
                features.get("selection_mentioned", False),
                features.get("selection_sentiment"),
                features.get("selection_signal"),
                features.get("role_mentioned", False),
                features.get("role_sentiment"),
                features.get("role_signal"),
                features.get("form_mentioned", False),
                features.get("form_sentiment"),
                features.get("form_signal"),
                features.get("captaincy_mentioned", False),
                features.get("captaincy_sentiment"),
                features.get("captaincy_signal"),
                features.get("load_mentioned", False),
                features.get("load_sentiment"),
                features.get("load_signal"),
                features.get("coaching_mentioned", False),
                features.get("coaching_sentiment"),
                features.get("coaching_signal"),
                features.get("captain_rating"),
                features.get("risk_level"),
                features.get("trade_signal"),
                features.get("injury_risk_score"),
                features.get("form_score"),
                features.get("selection_certainty"),
                features.get("upside_potential"),
                features.get("floor_safety"),
                features.get("total_article_count", 0),
                features.get("overall_sentiment"),
                features.get("overall_signal_strength"),
                features.get("confidence")
            ))
