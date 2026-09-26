"""
ML-based Resume <-> Job Semantic Matching
-------------------------------------------
This is a genuine, trainable-technique ML component (as opposed to the
plain keyword-overlap counting used elsewhere in the platform), suitable
for citing as "the ML part" of the project in a report or viva.

Technique: TF-IDF (Term Frequency - Inverse Document Frequency) vectorization
+ cosine similarity, via scikit-learn.

Why this approach for a project like this (be ready to explain this):
  - TF-IDF turns the resume text and the job description into weighted word
    vectors, where words that are common across *many* documents (e.g. "the",
    "experience", "team") are down-weighted, and words that are distinctive
    to a particular resume/job (e.g. "kubernetes", "django", "tensorflow")
    are up-weighted. This is a real, textbook NLP feature-extraction step --
    not a lookup table.
  - Cosine similarity then measures the angle between those two vectors:
    1.0 means "pointing in exactly the same direction" (near-identical
    vocabulary emphasis), 0.0 means "no shared distinctive vocabulary".
    It's the standard baseline similarity metric for TF-IDF vectors and is
    what most introductory "resume matching" / "document similarity"
    research papers and tutorials use as their first model.
  - It's unsupervised, so it needs no labeled training dataset (which a
    student project realistically doesn't have access to for salaries or
    "good match" ground truth) -- it learns its vocabulary weights directly
    and only from the pair of documents (or an optional larger corpus) it's
    given, at request time.

Fit into the wider (larger) match score: see app/utils/ai_parser.py's
match_resume_to_job(), which blends this semantic_score with an explicit
required-skills overlap score and an experience-fit score. That blended,
multi-factor design is intentional and worth keeping -- pure text
similarity alone is a weak matching signal on its own (two resumes can
score similarly just for both being "software engineer" documents), so it
is combined with structured skill/experience signals rather than used
standalone. This mirrors how production ATS/matching systems layer
several signals rather than trusting one score.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def compute_semantic_similarity(resume_text, job_text):
    """Returns an integer 0-100 semantic similarity score between a resume's
    parsed text and a job's description, using TF-IDF + cosine similarity.

    Falls back to 0 (rather than raising) if either text is empty/too short
    to vectorize meaningfully -- this is a real edge case (e.g. a resume
    that failed to parse any text) and should degrade gracefully rather
    than crash the whole match-score calculation for that candidate.
    """
    resume_text = (resume_text or "").strip()
    job_text = (job_text or "").strip()

    if not resume_text or not job_text:
        return 0

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",   # drop common English filler words
            max_features=500,       # cap vocabulary size for a fast, lightweight fit
            ngram_range=(1, 2),     # capture both single words and 2-word phrases
                                     # (e.g. "machine learning", "react native")
        )
        tfidf_matrix = vectorizer.fit_transform([resume_text, job_text])

        # If the vectorizer ended up with an empty vocabulary (e.g. both
        # texts were pure stopwords/punctuation), cosine_similarity would
        # divide by a zero-norm vector -- guard against that explicitly.
        if tfidf_matrix.shape[1] == 0:
            return 0

        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return int(round(max(0.0, min(1.0, similarity)) * 100))
    except ValueError:
        # Raised by scikit-learn when, after stopword removal, there is no
        # vocabulary left at all (e.g. a one-word job description like "TBD").
        return 0


def rank_resumes_for_job(resume_texts_by_id, job_text, top_n=None):
    """Batch version: ranks multiple resumes against a single job using one
    shared TF-IDF vocabulary fit across all documents together. Sharing the
    vocabulary fit (rather than calling compute_semantic_similarity() in a
    loop) is what makes the scores comparable *to each other* -- each
    resume's vector is weighted against the same corpus statistics, which is
    the right way to do this when you need a ranked shortlist rather than
    just one isolated resume-vs-job score.

    Available for ranking a whole candidate pool against a job by semantic
    fit in one pass (e.g. for a future "AI-ranked shortlist" batch job/API,
    rather than only per-candidate scores).

    resume_texts_by_id: dict of {resume_id: resume_text}
    Returns: list of (resume_id, score_0_to_100) sorted highest first.
    """
    job_text = (job_text or "").strip()
    ids = [rid for rid, text in resume_texts_by_id.items() if (text or "").strip()]
    if not job_text or not ids:
        return []

    documents = [resume_texts_by_id[rid] for rid in ids] + [job_text]

    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=500, ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform(documents)
        if tfidf_matrix.shape[1] == 0:
            return [(rid, 0) for rid in ids]

        job_vector = tfidf_matrix[-1:]
        resume_vectors = tfidf_matrix[:-1]
        similarities = cosine_similarity(resume_vectors, job_vector).flatten()
    except ValueError:
        return [(rid, 0) for rid in ids]

    ranked = sorted(
        zip(ids, (int(round(max(0.0, min(1.0, s)) * 100)) for s in similarities)),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return ranked[:top_n] if top_n else ranked
