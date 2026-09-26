"""
AI Cover Letter Generator
----------------------------
Template-based generation, not a call to an external LLM API (which would
mean an ongoing paid dependency and API-key management this project
doesn't have). This produces a genuinely structured, personalized letter
by filling a professional template with real specifics: the candidate's
name, the job title/company, and their actual matched skills for that
role -- rather than generic filler text.

Honest framing if asked: this is templated text generation with
conditional logic, not a generative language model. It's explainable and
deterministic -- the same inputs always produce the same structure.
"""


def generate_cover_letter(candidate_name, job_title, company_name, matched_skills, years_experience=None):
    matched_skills = matched_skills or []
    company_name = company_name or "your company"

    skills_phrase = ""
    if len(matched_skills) >= 3:
        skills_phrase = f"{', '.join(matched_skills[:-1])}, and {matched_skills[-1]}"
    elif len(matched_skills) == 2:
        skills_phrase = f"{matched_skills[0]} and {matched_skills[1]}"
    elif len(matched_skills) == 1:
        skills_phrase = matched_skills[0]

    experience_phrase = ""
    if years_experience and years_experience > 0:
        experience_phrase = f" with {years_experience}+ year{'s' if years_experience != 1 else ''} of hands-on experience"

    body_skills_para = ""
    if skills_phrase:
        body_skills_para = (
            f"My background{experience_phrase} in {skills_phrase} aligns directly with what this role requires. "
            f"I've applied these skills in real projects rather than just coursework, and I'm confident I can "
            f"contribute from day one."
        )
    else:
        body_skills_para = (
            f"I bring a strong, adaptable technical foundation{experience_phrase} and a genuine eagerness to grow "
            f"into this role's specific requirements quickly."
        )

    letter = f"""Dear Hiring Manager,

I am writing to express my interest in the {job_title} position at {company_name}. Having reviewed the role's requirements, I believe my skills and experience make me a strong fit for this opportunity.

{body_skills_para}

Beyond technical skills, I bring genuine curiosity and a habit of following through -- qualities that show up in how I approach every project I take on. I would welcome the opportunity to discuss how I can contribute to {company_name}'s team.

Thank you for considering my application. I look forward to the possibility of discussing this role further.

Sincerely,
{candidate_name}"""

    return letter
