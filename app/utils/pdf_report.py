"""
PDF Report Generator
---------------------
Produces polished, downloadable PDF reports so both candidates and recruiters
can take RecruitSmart's AI analysis outside the browser (for portfolios,
placement cells, or hiring committee reviews). Built with reportlab so it has
no external system dependencies (e.g. no wkhtmltopdf/Chrome needed).

Two report types are provided:
  - generate_candidate_report(): resume + ATS + (optional) match + (optional)
    GitHub verification summary for a single candidate.
  - generate_shortlist_report(): a ranked candidate table for a recruiter,
    for a specific job posting.
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER

PRIMARY = colors.HexColor("#6366f1")
DARK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#64748b")
SUCCESS = colors.HexColor("#10b981")
WARNING = colors.HexColor("#f59e0b")
DANGER = colors.HexColor("#ef4444")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RSTitle", fontSize=20, textColor=PRIMARY, spaceAfter=4, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="RSSubtitle", fontSize=10, textColor=MUTED, spaceAfter=14))
    styles.add(ParagraphStyle(name="RSSection", fontSize=13, textColor=DARK, spaceBefore=16, spaceAfter=8, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="RSBody", fontSize=10, textColor=DARK, leading=15))
    styles.add(ParagraphStyle(name="RSMuted", fontSize=9, textColor=MUTED))
    styles.add(ParagraphStyle(name="RSScoreBig", fontSize=32, textColor=PRIMARY, alignment=TA_CENTER, fontName="Helvetica-Bold"))
    return styles


def _score_color(score):
    if score >= 75:
        return SUCCESS
    if score >= 50:
        return WARNING
    return DANGER


def _header(elements, styles, title, subtitle):
    elements.append(Paragraph("RecruitSmart", styles["RSTitle"]))
    elements.append(Paragraph(title, ParagraphStyle(name="h2", fontSize=14, textColor=DARK, fontName="Helvetica-Bold")))
    elements.append(Paragraph(subtitle, styles["RSSubtitle"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    elements.append(Spacer(1, 10))


def _skill_chip_table(skills, empty_text="None recorded"):
    if not skills:
        return Paragraph(empty_text, ParagraphStyle(name="empty", fontSize=9, textColor=MUTED))
    rows, row = [], []
    for i, skill in enumerate(skills, 1):
        row.append(skill)
        if i % 4 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    t = Table(rows, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def generate_candidate_report(user, resume, match_score=None, job=None, github_data=None):
    """Build a candidate-facing PDF: ATS analysis, optional job-match
    breakdown, and optional GitHub portfolio verification. Returns a BytesIO
    buffer ready to be sent with Flask's send_file()."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    styles = _styles()
    elements = []

    subtitle = f"Candidate Report for {user.get_full_name()} &nbsp;|&nbsp; Generated {datetime.utcnow().strftime('%d %b %Y')}"
    _header(elements, styles, "Candidate Evaluation Report", subtitle)

    # --- ATS Score summary ---
    elements.append(Paragraph("Resume ATS Score", styles["RSSection"]))
    score_color = _score_color(resume.ats_score or 0)
    score_table = Table([[Paragraph(f"<font color='{score_color.hexval()}'>{resume.ats_score or 0}%</font>",
                                     styles["RSScoreBig"])]], colWidths=[60 * mm])
    score_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    elements.append(score_table)
    elements.append(Spacer(1, 6))
    for tip in (resume.get_ats_feedback_list() or [])[:6]:
        elements.append(Paragraph(f"• {tip}", styles["RSBody"]))

    elements.append(Paragraph("Extracted Skills", styles["RSSection"]))
    elements.append(_skill_chip_table(resume.get_skills_list()))

    # --- Resume Authenticity Check (optional) ---
    if getattr(resume, 'authenticity_score', None) is not None:
        elements.append(Paragraph("Resume Authenticity Check", styles["RSSection"]))
        auth_color = _score_color(resume.authenticity_score)
        elements.append(Paragraph(
            f"<font color='{auth_color.hexval()}'><b>{resume.authenticity_tier}</b></font> &mdash; {resume.authenticity_score}/100",
            styles["RSBody"]))
        flags = resume.get_authenticity_flags() if hasattr(resume, 'get_authenticity_flags') else []
        if flags:
            for flag in flags[:5]:
                elements.append(Paragraph(f"• {flag}", styles["RSBody"]))
        else:
            elements.append(Paragraph("No inconsistencies detected across 4 automated checks (timeline, PDF metadata, content authenticity, duplicate detection).", styles["RSBody"]))
        elements.append(Spacer(1, 4))

    # --- Job match section (optional) ---
    if match_score and job:
        elements.append(Paragraph(f"Job Match: {job.title}", styles["RSSection"]))
        rows = [
            ["Overall Match", f"{match_score.overall_score}%"],
            ["Skill Match", f"{match_score.skill_score}%"],
            ["Semantic Relevance", f"{match_score.semantic_score}%"],
            ["Experience Fit", f"{match_score.experience_score}%"],
            ["Recommendation", (match_score.recommendation or "").replace("_", " ").title()],
        ]
        if getattr(match_score, "ontology_score", None) is not None:
            rows.insert(3, ["Skill Ontology Match", f"{match_score.ontology_score}%"])
        t = Table(rows, colWidths=[70 * mm, 70 * mm])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("Matching Skills", styles["RSBody"]))
        elements.append(_skill_chip_table(match_score.get_matching_skills_list()))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("Missing Skills (Skill Gap)", styles["RSBody"]))
        elements.append(_skill_chip_table(match_score.get_missing_skills_list(), empty_text="No gaps detected"))

        explanation = match_score.get_explanation_data() if hasattr(match_score, "get_explanation_data") else {}
        if explanation.get("reasons"):
            elements.append(Spacer(1, 6))
            elements.append(Paragraph("Why This Score", styles["RSBody"]))
            for reason in explanation["reasons"]:
                text = reason.get("text") if isinstance(reason, dict) else reason
                elements.append(Paragraph(f"• {text}", styles["RSBody"]))
        if explanation.get("counterfactuals"):
            elements.append(Spacer(1, 6))
            elements.append(Paragraph("What Could Improve This Match", styles["RSBody"]))
            for c in explanation["counterfactuals"]:
                elements.append(Paragraph(
                    f"• Add {c['skill']} -> estimated {c['estimated_overall_score']}%", styles["RSBody"]))

    # --- GitHub verification section (optional) ---
    if github_data and not github_data.get("error"):
        elements.append(Paragraph("GitHub Portfolio Verification", styles["RSSection"]))
        a = github_data["analytics"]
        rows = [
            ["GitHub Username", github_data["username"]],
            ["Portfolio Authenticity Score", f"{github_data['score']}/100 ({github_data['tier']})"],
            ["Public Repositories", str(a["public_repos"])],
            ["Total Stars Earned", str(a["total_stars"])],
            ["Followers", str(a["followers"])],
            ["Resume-Claimed Skills Confirmed by Code", f"{github_data['skill_comparison']['authenticity_rate']}%"],
        ]
        t = Table(rows, colWidths=[80 * mm, 60 * mm])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("Verified Skills (backed by public repositories)", styles["RSBody"]))
        elements.append(_skill_chip_table(a["verified_skills"]))

    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    elements.append(Paragraph(
        "Generated automatically by RecruitSmart — an intelligent recruitment and candidate evaluation platform.",
        styles["RSMuted"]))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_shortlist_report(job, match_scores):
    """Build a recruiter-facing PDF ranking every candidate matched to a job,
    sorted by overall AI match score. match_scores is a list of MatchScore
    objects (each with a related .resume -> .user)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    styles = _styles()
    elements = []

    subtitle = f"Ranked Candidate Shortlist &nbsp;|&nbsp; Generated {datetime.utcnow().strftime('%d %b %Y')}"
    _header(elements, styles, f"Job: {job.title}", subtitle)

    elements.append(Paragraph(f"{job.location or 'Remote'} &nbsp;•&nbsp; {job.job_type.replace('_', ' ').title()} "
                               f"&nbsp;•&nbsp; {len(match_scores)} candidates evaluated", styles["RSBody"]))
    elements.append(Spacer(1, 10))

    sorted_matches = sorted(match_scores, key=lambda m: m.overall_score, reverse=True)
    data = [["Rank", "Candidate", "Overall", "Skills", "Experience", "Recommendation"]]
    for i, m in enumerate(sorted_matches, 1):
        candidate_name = m.resume.user.get_full_name() if m.resume and m.resume.user else "Unknown"
        data.append([
            str(i), candidate_name, f"{m.overall_score}%", f"{m.skill_score}%",
            f"{m.experience_score}%", (m.recommendation or "-").replace("_", " ").title()
        ])

    t = Table(data, colWidths=[14 * mm, 46 * mm, 22 * mm, 22 * mm, 26 * mm, 34 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    elements.append(t)

    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    elements.append(Paragraph(
        "Generated automatically by RecruitSmart. Scores are AI-assisted signals to support, not replace, human hiring judgment.",
        styles["RSMuted"]))

    doc.build(elements)
    buffer.seek(0)
    return buffer
