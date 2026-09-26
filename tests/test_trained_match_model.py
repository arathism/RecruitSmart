"""Tests for the trained Match Confidence Classifier
(app/utils/train_match_model.py + app/utils/trained_match_model.py) --
the project's one genuinely supervised, trained-and-persisted ML component.
"""
import os
import importlib

import app.utils.trained_match_model as trained_match_model
from app.utils.train_match_model import (
    train_and_save, MODEL_PATH, METADATA_PATH, FEATURE_NAMES, _generate_synthetic_dataset,
)


class TestSyntheticDataset:
    def test_generates_expected_shape(self):
        X, y = _generate_synthetic_dataset(n_samples=500)
        assert X.shape == (500, len(FEATURE_NAMES))
        assert y.shape == (500,)

    def test_labels_are_binary(self):
        _, y = _generate_synthetic_dataset(n_samples=500)
        assert set(y.tolist()) <= {0, 1}

    def test_features_within_expected_range(self):
        X, _ = _generate_synthetic_dataset(n_samples=500)
        assert X.min() >= 0
        assert X.max() <= 100

    def test_both_classes_present(self):
        # A degenerate all-one-class dataset would make the model
        # meaningless -- guard against that regressing silently.
        _, y = _generate_synthetic_dataset(n_samples=2000)
        assert 0 in y and 1 in y


class TestTrainAndSave:
    def test_train_and_save_produces_model_file(self, tmp_path, monkeypatch):
        # Train into a throwaway path so this test doesn't clobber the
        # real committed model artifact.
        fake_model_path = tmp_path / "model.pkl"
        fake_meta_path = tmp_path / "model.meta.json"
        monkeypatch.setattr("app.utils.train_match_model.MODEL_PATH", str(fake_model_path))
        monkeypatch.setattr("app.utils.train_match_model.METADATA_PATH", str(fake_meta_path))
        metadata = train_and_save()
        assert fake_model_path.exists()
        assert fake_meta_path.exists()
        assert metadata["label_source"].startswith("synthetic")
        assert metadata["model_type"] in ("LogisticRegression", "GradientBoostingClassifier")
        assert 0.5 <= metadata["test_roc_auc"] <= 1.0

    def test_committed_model_artifact_exists(self):
        # The trained model this project ships with should already be on
        # disk -- if this fails, someone needs to re-run
        # `python -m app.utils.train_match_model`.
        assert os.path.exists(MODEL_PATH), "Run `python -m app.utils.train_match_model` to (re)train the shipped model"
        assert os.path.exists(METADATA_PATH)


class TestPredictMatchConfidence:
    def setup_method(self):
        # Force a fresh load in case another test module already cached
        # a loaded/unloaded state on the shared module.
        importlib.reload(trained_match_model)

    def test_returns_confidence_when_model_available(self):
        result = trained_match_model.predict_match_confidence(
            skill_score=85, semantic_score=70, experience_score=80, authenticity_score=90,
        )
        assert result["model_available"] is True
        assert isinstance(result["confidence"], int)
        assert 0 <= result["confidence"] <= 100

    def test_strong_profile_scores_higher_than_weak_profile(self):
        strong = trained_match_model.predict_match_confidence(
            skill_score=95, semantic_score=90, experience_score=95, authenticity_score=95,
        )
        weak = trained_match_model.predict_match_confidence(
            skill_score=10, semantic_score=15, experience_score=10, authenticity_score=90,
        )
        assert strong["confidence"] > weak["confidence"]

    def test_low_authenticity_pulls_confidence_down(self):
        # Sanity-check the authenticity-gate effect baked into training:
        # holding skill/semantic/experience fixed, a low authenticity
        # score should not produce a *higher* confidence than a high one.
        high_auth = trained_match_model.predict_match_confidence(
            skill_score=80, semantic_score=70, experience_score=75, authenticity_score=95,
        )
        low_auth = trained_match_model.predict_match_confidence(
            skill_score=80, semantic_score=70, experience_score=75, authenticity_score=10,
        )
        assert low_auth["confidence"] <= high_auth["confidence"]

    def test_missing_authenticity_score_does_not_crash(self):
        result = trained_match_model.predict_match_confidence(
            skill_score=60, semantic_score=50, experience_score=55, authenticity_score=None,
        )
        assert result["model_available"] is True
        assert result["confidence"] is not None

    def test_gracefully_degrades_when_model_file_missing(self, monkeypatch):
        monkeypatch.setattr(trained_match_model, "_model", None)
        monkeypatch.setattr(trained_match_model, "_load_attempted", True)
        result = trained_match_model.predict_match_confidence(
            skill_score=80, semantic_score=70, experience_score=75, authenticity_score=90,
        )
        assert result == {"confidence": None, "model_available": False, "model_type": None}


class TestGetModelMetadata:
    def test_returns_metadata_dict(self):
        importlib.reload(trained_match_model)
        metadata = trained_match_model.get_model_metadata()
        assert metadata is not None
        assert "feature_names" in metadata
        assert metadata["feature_names"] == FEATURE_NAMES
