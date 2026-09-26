"""
GitHub Portfolio Verification Engine
--------------------------------------
This module is the core of RecruitSmart's "Verified Skills" feature. Instead of
trusting a candidate's self-reported resume skills at face value, it cross-checks
those claims against real, publicly-verifiable engineering activity pulled from
the GitHub REST API (repositories, languages used, stars earned, commit recency).

This directly targets one of the biggest weaknesses of ordinary ATS tools: they
score a resume on keyword density alone, which is trivial to game. RecruitSmart
instead produces a Portfolio Authenticity Score that recruiters can trust, and
gives candidates an incentive to actually build things rather than just list
buzzwords.

No API key is required for the read-only, unauthenticated GitHub endpoints used
here, but a GITHUB_TOKEN environment variable is honored if present, since it
raises the API rate limit from 60/hour to 5000/hour.
"""
import os
import json
import requests

GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 8

# Maps GitHub's linguist language names to the skill vocabulary already used
# elsewhere in the app (app/utils/ai_parser.py) so verification can be matched
# against resume-extracted skills.
LANGUAGE_SKILL_MAP = {
    "python": "python", "javascript": "javascript", "typescript": "javascript",
    "java": "java", "c++": "c++", "c#": "c#", "go": "go", "rust": "rust",
    "ruby": "ruby", "php": "php", "html": "html", "css": "css",
    "shell": "bash", "dockerfile": "docker", "jupyter notebook": "python",
}


def _headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_github_profile(username):
    """Fetch a GitHub user's public profile and repositories.

    Returns a dict with a top-level 'error' key on failure, otherwise a dict
    containing the raw profile info plus up to 100 of the user's repos.
    """
    username = (username or "").strip().lstrip("@")
    if not username:
        return {"error": "No GitHub username provided."}

    try:
        profile_resp = requests.get(
            f"{GITHUB_API_BASE}/users/{username}", headers=_headers(), timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException:
        return {"error": "Could not reach GitHub. Please check your connection and try again."}

    if profile_resp.status_code == 404:
        return {"error": f'GitHub user "{username}" was not found.'}
    if profile_resp.status_code == 403:
        return {"error": "GitHub API rate limit reached. Please try again in a few minutes."}
    if profile_resp.status_code != 200:
        return {"error": f"GitHub API returned an unexpected error ({profile_resp.status_code})."}

    profile = profile_resp.json()

    try:
        repos_resp = requests.get(
            f"{GITHUB_API_BASE}/users/{username}/repos",
            headers=_headers(),
            params={"per_page": 100, "sort": "updated"},
            timeout=REQUEST_TIMEOUT,
        )
        repos = repos_resp.json() if repos_resp.status_code == 200 else []
    except requests.RequestException:
        repos = []

    if not isinstance(repos, list):
        repos = []

    return {"profile": profile, "repos": repos}


# Framework/library manifest files worth reading, and the dependency-name ->
# skill-vocabulary mapping for each. This is what lets verification catch
# frameworks (React, Flask, Spring...) instead of only programming languages,
# which is the single biggest gap in a language-only verification approach.
DEPENDENCY_FILES = {
    "package.json": {
        "react": "react", "next": "next.js", "vue": "vue", "@angular/core": "angular",
        "express": "express", "redux": "redux", "tailwindcss": "tailwind",
        "nestjs": "nestjs", "socket.io": "socket.io", "mongoose": "mongodb",
    },
    "requirements.txt": {
        "flask": "flask", "django": "django", "fastapi": "fastapi", "numpy": "numpy",
        "pandas": "pandas", "tensorflow": "tensorflow", "torch": "pytorch",
        "scikit-learn": "scikit-learn", "opencv-python": "opencv", "mediapipe": "mediapipe",
        "requests": "python", "flask-sqlalchemy": "flask",
    },
    "Pipfile": {
        "flask": "flask", "django": "django", "fastapi": "fastapi",
    },
    "pom.xml": {
        "spring": "spring", "hibernate": "hibernate", "junit": "junit",
    },
    "build.gradle": {
        "spring": "spring", "junit": "junit",
    },
    "Gemfile": {
        "rails": "rails", "sinatra": "sinatra",
    },
    "go.mod": {
        "gin-gonic": "go", "labstack/echo": "go",
    },
    "Cargo.toml": {
        "actix-web": "rust", "tokio": "rust",
    },
    "composer.json": {
        "laravel": "laravel", "symfony": "symfony",
    },
}


def fetch_repo_dependency_skills(username, repos, max_repos=5):
    """Reads real dependency-manifest files (package.json, requirements.txt,
    etc.) from a candidate's most-recently-updated repos to detect actual
    frameworks/libraries used -- not just programming languages. This closes
    the biggest gap in language-only GitHub verification: a candidate who has
    genuinely built things with React or Flask previously had no way to get
    that confirmed, since GitHub's language stats only report the underlying
    language (JavaScript/Python), never the framework.

    Only checks a handful of the most recently active repos to keep this
    fast and within API rate limits during a live demo.
    """
    found_skills = set()
    own_repos = [r for r in repos if not r.get("fork")]
    recent_repos = sorted(own_repos, key=lambda r: r.get("updated_at", ""), reverse=True)[:max_repos]

    for repo in recent_repos:
        repo_name = repo.get("name")
        if not repo_name:
            continue
        try:
            listing_resp = requests.get(
                f"{GITHUB_API_BASE}/repos/{username}/{repo_name}/contents/",
                headers=_headers(), timeout=REQUEST_TIMEOUT,
            )
            if listing_resp.status_code != 200:
                continue
            files_in_repo = {f.get("name"): f.get("download_url") for f in listing_resp.json() if isinstance(f, dict)}
        except (requests.RequestException, ValueError):
            continue

        for manifest_name, dependency_map in DEPENDENCY_FILES.items():
            download_url = files_in_repo.get(manifest_name)
            if not download_url:
                continue
            try:
                # raw.githubusercontent.com content downloads don't count
                # against the api.github.com rate limit, so this stays cheap
                # even across several repos.
                file_resp = requests.get(download_url, timeout=REQUEST_TIMEOUT)
                content_lower = file_resp.text.lower()
            except requests.RequestException:
                continue

            for dependency_name, skill_name in dependency_map.items():
                if dependency_name.lower() in content_lower:
                    found_skills.add(skill_name)

    return found_skills


def analyze_portfolio(profile, repos):
    """Turn raw GitHub API data into portfolio analytics: languages, stars,
    top repos, activity recency, and a set of skills verified by real code."""
    own_repos = [r for r in repos if not r.get("fork")]

    language_counts = {}
    total_stars = 0
    total_forks = 0
    for repo in own_repos:
        lang = repo.get("language")
        if lang:
            language_counts[lang] = language_counts.get(lang, 0) + 1
        total_stars += repo.get("stargazers_count", 0) or 0
        total_forks += repo.get("forks_count", 0) or 0

    top_languages = sorted(language_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]

    verified_skills = set()
    for lang, _count in top_languages:
        mapped = LANGUAGE_SKILL_MAP.get(lang.lower())
        if mapped:
            verified_skills.add(mapped)

    top_repos = sorted(
        own_repos, key=lambda r: (r.get("stargazers_count", 0), r.get("updated_at", "")), reverse=True
    )[:6]
    top_repos_data = [
        {
            "name": r.get("name"),
            "description": r.get("description") or "No description provided.",
            "url": r.get("html_url"),
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "language": r.get("language") or "N/A",
            "updated_at": r.get("updated_at", "")[:10],
        }
        for r in top_repos
    ]

    return {
        "public_repos": profile.get("public_repos", 0),
        "followers": profile.get("followers", 0),
        "following": profile.get("following", 0),
        "account_created": (profile.get("created_at") or "")[:10],
        "total_stars": total_stars,
        "total_forks": total_forks,
        "own_repo_count": len(own_repos),
        "top_languages": [{"name": lang, "repo_count": count} for lang, count in top_languages],
        "verified_skills": sorted(verified_skills),
        "top_repos": top_repos_data,
    }


def compute_portfolio_score(analytics):
    """A transparent, explainable 0-100 score combining activity, popularity,
    and consistency signals. Weighted so no single metric can be gamed by
    forking/starring alone."""
    repo_score = min(30, analytics["own_repo_count"] * 3)
    star_score = min(25, analytics["total_stars"] * 2)
    follower_score = min(15, analytics["followers"])
    diversity_score = min(15, len(analytics["top_languages"]) * 3)
    activity_score = 15 if analytics["own_repo_count"] >= 3 else analytics["own_repo_count"] * 5

    total = repo_score + star_score + follower_score + diversity_score + activity_score
    total = max(0, min(100, round(total)))

    if total >= 80:
        tier = "Excellent"
    elif total >= 60:
        tier = "Strong"
    elif total >= 35:
        tier = "Developing"
    else:
        tier = "Limited"

    breakdown = {
        "repository_activity": repo_score,
        "community_recognition": star_score,
        "network_reach": follower_score,
        "language_diversity": diversity_score,
        "consistency": activity_score,
    }
    return total, tier, breakdown


def cross_reference_resume_skills(resume_skills, verified_skills):
    """Compare resume-claimed skills against GitHub-verified skills and flag
    claims that have no supporting public evidence. This is the anti-bias /
    anti-exaggeration mechanism that differentiates RecruitSmart from a plain
    keyword-matching ATS.

    Both sides are normalized through app.utils.ai_parser.normalize_skill
    first, so equivalent spellings (e.g. a resume that says "React.js" vs
    GitHub's canonical "react") count as the same skill rather than one
    unfairly showing up as "unconfirmed" just because of how it was typed.
    """
    from app.utils.ai_parser import normalize_skill

    resume_set = set(normalize_skill(s) for s in (resume_skills or []))
    verified_set = set(normalize_skill(s) for s in (verified_skills or []))

    confirmed = sorted(resume_set & verified_set)
    unconfirmed = sorted(resume_set - verified_set)
    bonus = sorted(verified_set - resume_set)

    if resume_set:
        authenticity_rate = round((len(confirmed) / len(resume_set)) * 100)
    else:
        authenticity_rate = 0

    return {
        "confirmed_skills": confirmed,
        "unconfirmed_skills": unconfirmed,
        "bonus_verified_skills": bonus,
        "authenticity_rate": authenticity_rate,
    }


def verify_github_portfolio(username, resume_skills=None):
    """High-level entry point used by routes: fetch, analyze, score, and
    cross-reference in one call. Returns a dict with 'error' on failure."""
    result = fetch_github_profile(username)
    if "error" in result:
        return result

    analytics = analyze_portfolio(result["profile"], result["repos"])

    # Beyond languages: read actual dependency manifests from recent repos to
    # confirm real framework/library usage (React, Flask, Spring, etc.), not
    # just the underlying programming language.
    framework_skills = fetch_repo_dependency_skills(result["profile"].get("login", username), result["repos"])
    if framework_skills:
        analytics["verified_skills"] = sorted(set(analytics["verified_skills"]) | framework_skills)
        analytics["framework_skills_detected"] = sorted(framework_skills)
    else:
        analytics["framework_skills_detected"] = []

    score, tier, breakdown = compute_portfolio_score(analytics)
    comparison = cross_reference_resume_skills(resume_skills, analytics["verified_skills"])

    return {
        "username": result["profile"].get("login", username),
        "name": result["profile"].get("name") or result["profile"].get("login", username),
        "avatar_url": result["profile"].get("avatar_url"),
        "profile_url": result["profile"].get("html_url"),
        "bio": result["profile"].get("bio"),
        "analytics": analytics,
        "score": score,
        "tier": tier,
        "score_breakdown": breakdown,
        "skill_comparison": comparison,
    }
