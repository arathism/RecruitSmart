"""
Resume Authenticity Checker
-----------------------------
Answers the question every ATS conveniently avoids: "the keywords match, but
is this resume actually genuine?" Plain ATS scoring (see ai_parser.py) only
checks whether a resume *contains* the right words -- it has no opinion on
whether the document is truthful, internally consistent, or even original.

This module adds a second, independent signal: a heuristic Authenticity Score
built from four real, explainable checks:

  1. Timeline consistency  - overlapping "full-time" date ranges, dates in
     the future, or a claimed total-experience figure that doesn't match the
     sum of the date ranges actually printed on the resume.
  2. PDF metadata forensics - a resume's PDF container carries creation/
     modification timestamps and author/producer fields. Impossible
     timestamps (modified before it was "created") or an author name that
     doesn't match the account holder at all are real, checkable signals.
  3. Content-authenticity heuristics - buzzword density vs. concrete detail
     (numbers, named tools, named companies). A resume that is 90% "results-
     driven team player" and 10% substance is a known template/AI-filler
     pattern.
  4. Duplicate / template-reuse detection - fuzzy-matches this resume's text
     against every other resume already on the platform. A near-identical
     match to a *different* candidate's resume is a strong, cheap signal of
     copy-pasted or purchased resume content.

IMPORTANT (and this is the honest framing to use in a viva/publication):
this is a heuristic *screening* tool, like a plagiarism checker -- it flags
patterns worth a human's attention, it does not "prove" fraud. The score and
flags are explainable by design so a recruiter (or an examiner) can see
exactly which of the 4 checks fired and why.
"""
import re
import difflib
from datetime import datetime

CURRENT_YEAR = datetime.utcnow().year

GENERIC_BUZZWORDS = [
    "hardworking", "team player", "results-driven", "results driven", "go-getter",
    "detail-oriented", "detail oriented", "self-starter", "self starter", "dynamic",
    "synergy", "think outside the box", "fast learner", "passionate", "motivated individual",
    "excellent communication skills", "proven track record", "hard working",
    "highly motivated", "strong work ethic", "people person",
]

CONCRETE_SIGNAL_PATTERN = re.compile(
    r"(\d+%|\$\d|\d+x\b|\bincreased\b|\bdecreased\b|\breduced\b|\bimproved\b|"
    r"\bbuilt\b|\bshipped\b|\bdeployed\b|\bmigrated\b|\bled a team of \d+|"
    r"\d+\s*(users|customers|clients|requests|records|rows|servers))",
    re.IGNORECASE,
)

DATE_RANGE_PATTERN = re.compile(r"(19|20)\d{2}\s*[-–—]\s*((19|20)\d{2}|present|current)", re.IGNORECASE)

# Words that, if they appear on the same line as a date range (or the line
# just above it), mean "this is an education entry, not a job" -- an
# ongoing degree legitimately lists its *expected* graduation year, which
# is always in the future relative to "today" for any student who hasn't
# graduated yet. That is completely normal and should never be treated the
# same as a fabricated future *employment* date. Flagging every CS student's
# resume as "suspicious" for stating their own expected graduation year was
# a real false-positive bug, not a hypothetical edge case -- it fires on any
# resume from a current student.
EDUCATION_CONTEXT_WORDS = re.compile(
    r"\b(b\.?e\.?|b\.?tech|b\.?sc|bachelor|m\.?tech|m\.?sc|master|mba|ph\.?d|"
    r"diploma|university|college|institute|school|cgpa|gpa|semester|"
    r"pre-university|puc|sslc|hsc|degree|graduat\w*)\b",
    re.IGNORECASE,
)


def _line_context(text, match_start, match_end):
    """Returns the text line(s) immediately surrounding a date-range match,
    used to tell an education entry apart from an employment entry without
    needing a full resume-section parser."""
    line_start = text.rfind("\n", 0, match_start)
    prev_line_start = text.rfind("\n", 0, line_start) if line_start != -1 else -1
    window_start = prev_line_start + 1 if prev_line_start != -1 else max(0, match_start - 120)
    line_end = text.find("\n", match_end)
    window_end = line_end if line_end != -1 else min(len(text), match_end + 40)
    return text[window_start:window_end]


def check_timeline_consistency(text, claimed_experience_years=None):
    flags = []
    penalty = 0
    ranges = []

    for match in DATE_RANGE_PATTERN.finditer(text):
        raw = match.group(0)
        parts = re.split(r"[-–—]", raw)
        try:
            start = int(re.search(r"(19|20)\d{2}", parts[0]).group(0))
            end_str = parts[1].strip().lower()
            end = CURRENT_YEAR if end_str in ("present", "current") else int(re.search(r"(19|20)\d{2}", end_str).group(0))
            is_education = bool(EDUCATION_CONTEXT_WORDS.search(_line_context(text, match.start(), match.end())))
            ranges.append((start, end, is_education))
        except Exception:
            continue

    for start, end, is_education in ranges:
        if is_education and end <= CURRENT_YEAR + 3:
            # An ongoing degree stating its expected graduation year (up to
            # a few years out) is normal and not a red flag -- skip it.
            pass
        elif start > CURRENT_YEAR or end > CURRENT_YEAR:
            flags.append(f"A date range ({start}\u2013{end}) extends into the future.")
            penalty += 20
        if end < start:
            flags.append(f"A date range ({start}\u2013{end}) ends before it starts.")
            penalty += 20

    # Overlapping full-time ranges (more than one role claimed concurrently).
    # Education ranges are excluded here too -- a student's degree years
    # legitimately overlap with internships/part-time work done during that
    # same period, which is normal and not a "two concurrent jobs" red flag.
    valid_ranges = sorted([(s, e) for s, e, is_edu in ranges if e >= s and not is_edu])
    for i in range(len(valid_ranges) - 1):
        cur_start, cur_end = valid_ranges[i]
        next_start, next_end = valid_ranges[i + 1]
        overlap = min(cur_end, next_end) - max(cur_start, next_start)
        if overlap > 1:  # allow 1 year of natural rounding overlap
            flags.append(f"Overlapping date ranges detected ({cur_start}\u2013{cur_end} and {next_start}\u2013{next_end}) \u2014 verify these aren't two concurrent full-time roles.")
            penalty += 15

    if claimed_experience_years and valid_ranges:
        span_total = sum(end - start for start, end in valid_ranges)
        if claimed_experience_years > span_total + 2 and span_total > 0:
            flags.append(f"Resume states ~{claimed_experience_years} years of experience, but the dated ranges on the resume only add up to about {span_total} years.")
            penalty += 15

    return min(penalty, 40), flags


def check_pdf_metadata(file_path, candidate_full_name=None):
    flags = []
    penalty = 0
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        meta = reader.metadata or {}
    except Exception:
        return 0, []  # Can't inspect metadata (e.g. not a PDF) -- no penalty, just no signal

    def _parse_pdf_date(raw):
        if not raw:
            return None
        raw = str(raw).replace("D:", "")[:14]
        try:
            return datetime.strptime(raw, "%Y%m%d%H%M%S")
        except Exception:
            return None

    created = _parse_pdf_date(meta.get('/CreationDate'))
    modified = _parse_pdf_date(meta.get('/ModDate'))

    if created and modified and modified < created:
        flags.append("This PDF's 'last modified' timestamp is earlier than its 'created' timestamp \u2014 the file's metadata has likely been altered or spoofed.")
        penalty += 20

    if created and created.year > CURRENT_YEAR:
        flags.append("This PDF's creation timestamp is in the future, which is not possible for a genuine file.")
        penalty += 20

    author = str(meta.get('/Author', '') or '').strip()
    # Word processors and PDF exporters routinely stamp a placeholder into
    # /Author when the user never set their name in that app's own settings
    # (e.g. LibreOffice defaults to literally "Un-named"; Word/Acrobat often
    # leave it blank; LaTeX/Overleaf exports frequently say "" or the OS
    # username). None of that is evidence the document was written by
    # someone else -- it just means the software's own identity field was
    # never configured. Only compare against real, non-placeholder names.
    KNOWN_PLACEHOLDER_AUTHORS = {
        "un-named", "unnamed", "unknown", "user", "administrator", "admin",
        "microsoft word", "microsoft office user", "windows user",
        "libreoffice", "openoffice", "latex", "pdflatex", "overleaf",
        "canva", "google docs", "pages", "n/a", "author", "guest",
    }
    if author and candidate_full_name and author.lower() not in KNOWN_PLACEHOLDER_AUTHORS:
        candidate_parts = set(candidate_full_name.lower().split())
        author_parts = set(re.split(r"[\s,._-]+", author.lower()))
        if candidate_parts and not (candidate_parts & author_parts):
            flags.append(f"The PDF's internal 'Author' metadata field says \u201c{author}\u201d, which doesn't match the account name ({candidate_full_name}) \u2014 this file may have originally been written by/for someone else.")
            penalty += 15

    return min(penalty, 30), flags


def check_content_authenticity(text):
    flags = []
    penalty = 0
    words = re.findall(r"[a-zA-Z]+", text)
    word_count = max(len(words), 1)

    buzzword_hits = sum(text.lower().count(b) for b in GENERIC_BUZZWORDS)
    buzzword_density = buzzword_hits / word_count * 100
    concrete_hits = len(CONCRETE_SIGNAL_PATTERN.findall(text))

    if buzzword_density > 2.5 and concrete_hits == 0 and word_count > 80:
        flags.append("The resume leans heavily on generic phrases (e.g. \u201cresults-driven,\u201d \u201cteam player\u201d) with no concrete numbers, metrics, or named tools/outcomes to back them up \u2014 a common pattern in templated or AI-generated filler text.")
        penalty += 15

    if word_count < 60:
        flags.append("The resume is very short, which makes it difficult to independently verify any of the claims made.")
        penalty += 10

    return min(penalty, 25), flags


def check_duplicate_content(text, other_resumes):
    """other_resumes: list of (user_id, parsed_text) tuples for every other
    resume already stored on the platform."""
    flags = []
    penalty = 0
    if not text or len(text.strip()) < 60:
        return 0, []

    best_ratio = 0.0
    for user_id, other_text in other_resumes:
        if not other_text or len(other_text.strip()) < 60:
            continue
        ratio = difflib.SequenceMatcher(None, text, other_text).quick_ratio()
        if ratio > best_ratio:
            best_ratio = ratio

    if best_ratio > 0.92:
        flags.append("This resume's text is nearly identical to another candidate's resume already on file \u2014 likely a shared/purchased template or, less innocently, copied content.")
        penalty += 30
    elif best_ratio > 0.80:
        flags.append("This resume's text is highly similar to another candidate's resume on file \u2014 worth a manual look.")
        penalty += 15

    return min(penalty, 30), flags


def analyze_resume_authenticity(text, file_path=None, file_type=None, candidate_full_name=None,
                                 claimed_experience_years=None, other_resumes=None):
    """Runs all four checks and combines them into a single explainable score.

    Returns: {score, tier, flags, checks_run}
    """
    all_flags = []
    total_penalty = 0

    p, f = check_timeline_consistency(text, claimed_experience_years)
    total_penalty += p; all_flags += f

    if file_type == 'pdf' and file_path:
        p, f = check_pdf_metadata(file_path, candidate_full_name)
        total_penalty += p; all_flags += f

    p, f = check_content_authenticity(text)
    total_penalty += p; all_flags += f

    p, f = check_duplicate_content(text, other_resumes or [])
    total_penalty += p; all_flags += f

    # De-duplicate flags while preserving order (repeated sections/OCR artifacts
    # can otherwise trigger the same check multiple times)
    seen = set()
    deduped_flags = []
    for flag in all_flags:
        if flag not in seen:
            seen.add(flag)
            deduped_flags.append(flag)
    all_flags = deduped_flags

    score = max(0, 100 - total_penalty)

    if score >= 85:
        tier = "High Confidence"
    elif score >= 60:
        tier = "Moderate Confidence"
    else:
        tier = "Needs Manual Review"

    return {
        "score": score,
        "tier": tier,
        "flags": all_flags,
        "checks_run": ["Timeline Consistency", "PDF Metadata Forensics", "Content Authenticity", "Duplicate/Template Detection"],
    }
