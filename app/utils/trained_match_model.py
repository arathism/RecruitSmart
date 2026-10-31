"""
Loads and serves the trained Match Confidence Classifier at request time.

This is the ONE genuinely trained-and-saved supervised ML component in
RecruitSmart -- see train_match_model.py for how it was built, what it was
trained on, and the honest limitation (synthetic labels, not real hiring
outcomes). Every other "AI" feature in the platform is either transparent
rule-based scoring or unsupervised TF-IDF similarity; this module is the
one place a `.fit(X, y)` against labeled data actually happened and the
result was persisted to disk for reuse.

Usage (see app/utils/ai_parser.py's match_resume_to_job for the real call site):
    from app.utils.trained_match_model import predict_match_confidence
    result = predict_match_confidence(skill_score=80, semantic_score=55,
                                       experience_score=70, authenticity_score=90)
    # result = {"confidence": 78, "model_available": True, "model_type": "LogisticRegression"}

Fails soft, on purpose: if the model file hasn't been trained/committed yet
(e.g. a fresh clone before anyone ran `python -m app.utils.train_match_model`),
this returns model_available=False rather than crashing the whole match-score
calculation -- the platform's rule-based overall_score never depends on this
model being present.
"""
import json
import os
import threading

from app.utils.train_match_model import MODEL_PATH, METADATA_PATH, FEATURE_NAMES

_model = None
_metadata = None
_lock = threading.Lock()
_load_attempted = False


def _load():
    global _model, _metadata, _load_attempted
    with _lock:
        if _load_attempted:
            return
        _load_attempted = True
        if not os.path.exists(MODEL_PATH):
            return
        try:
            import joblib
            _model = joblib.load(MODEL_PATH)
            if os.path.exists(METADATA_PATH):
                with open(METADATA_PATH) as f:
                    _metadata = json.load(f)
        except Exception:
            # Corrupt/incompatible model file (e.g. scikit-learn version
            # mismatch) -- degrade gracefully rather than 500 the request.
            _model = None
            _metadata = None


def predict_match_confidence(skill_score, semantic_score, experience_score, authenticity_score=None):
    """Returns {"confidence": int|None, "model_available": bool, "model_type": str|None}.

    confidence is the model's predicted probability (0-100) that this
    resume/job pairing is a "good match" per its training labels -- a
    supplementary, ML-native cross-check on the platform's primary
    rule-based overall_score, not a replacement for it.
    """
    _load()
    if _model is None:
        return {"confidence": None, "model_available": False, "model_type": None}

    # authenticity_score is optional at call sites that don't have a resume
    # object handy (e.g. a bulk ranking pass) -- default to a neutral 70
    # rather than 0, so missing data doesn't look like a fraud flag.
    features = [[
        max(0, min(100, skill_score)),
        max(0, min(100, semantic_score)),
        max(0, min(100, experience_score)),
        max(0, min(100, authenticity_score if authenticity_score is not None else 70)),
    ]]
    try:
        proba = _model.predict_proba(features)[0][1]
        confidence = int(round(proba * 100))
    except Exception:
        return {"confidence": None, "model_available": False, "model_type": None}

    return {
        "confidence": confidence,
        "model_available": True,
        "model_type": _metadata.get("model_type") if _metadata else type(_model).__name__,
    }


def get_model_metadata():
    """Returns the training metadata dict (metrics, feature names, label
    source) for display on an admin/about page, or None if untrained."""
    _load()
    return _metadata
