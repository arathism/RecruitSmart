"""
Skill Demand Dashboard
-------------------------
Shows which skills are actually most common across this platform's real
data -- nothing fabricated or predicted. Two honest, directly-countable
signals:

  1. "Candidate Supply" -- how many resumes on the platform list each skill
  2. "Employer Demand" -- how many active job postings require each skill

From these two real counts, a third derived (still honest) metric is
computed: a demand/supply gap -- skills employers want that relatively few
candidates currently list, which is a genuinely useful signal for both
recruiters (hard-to-fill roles) and candidates (what to learn next).

Deliberately NOT included here: anything requiring data this platform
doesn't actually have, like predicted future applicant counts or projected
future scores -- those would have to be fabricated, which is the opposite
of what this feature is for.
"""
from collections import Counter


def compute_skill_demand(all_resume_skills, all_job_skills, top_n=15):
    """all_resume_skills: list of skill-lists (one per resume)
       all_job_skills: list of skill-lists (one per active job)
       Returns: {supply: [(skill, count), ...], demand: [(skill, count), ...],
                 gap: [(skill, demand_count, supply_count), ...]}"""
    supply_counter = Counter()
    for skills in all_resume_skills:
        for s in skills:
            supply_counter[s.lower().strip()] += 1

    demand_counter = Counter()
    for skills in all_job_skills:
        for s in skills:
            demand_counter[s.lower().strip()] += 1

    supply_top = supply_counter.most_common(top_n)
    demand_top = demand_counter.most_common(top_n)

    # Gap: skills that appear in job postings but are proportionally scarce
    # among candidates -- ratio-based so it's fair regardless of how many
    # total resumes/jobs exist.
    total_resumes = max(len(all_resume_skills), 1)
    total_jobs = max(len(all_job_skills), 1)

    gaps = []
    for skill, demand_count in demand_counter.items():
        supply_count = supply_counter.get(skill, 0)
        demand_rate = demand_count / total_jobs
        supply_rate = supply_count / total_resumes
        if demand_rate > 0:
            scarcity = demand_rate - supply_rate
            gaps.append((skill, demand_count, supply_count, scarcity))

    gaps.sort(key=lambda x: x[3], reverse=True)
    top_gaps = [(skill, d, s) for skill, d, s, _ in gaps[:top_n] if _ > 0]

    return {
        "supply": supply_top,
        "demand": demand_top,
        "gap": top_gaps,
        "total_resumes": len(all_resume_skills),
        "total_jobs": len(all_job_skills),
    }
