"""
AI Interview Question Generator
----------------------------------
Rule-based, not a call to an external LLM API -- same honest framing as the
cover letter generator. Questions are pulled from a curated bank keyed by
skill, plus a fixed set of role-agnostic behavioral questions. This is
deterministic and explainable: the same job title + skills always produce
the same question set, and every question can be traced to which skill (or
which category) it's testing.
"""

TECHNICAL_QUESTION_BANK = {
    "python": [
        "What's the difference between a list and a tuple in Python, and when would you use each?",
        "Explain how Python's garbage collection works, at a high level.",
        "What are Python decorators, and can you describe a situation where you'd use one?",
    ],
    "java": [
        "What's the difference between an abstract class and an interface in Java?",
        "Explain how Java's garbage collection differs from manual memory management.",
        "What is the difference between '==' and '.equals()' when comparing objects?",
    ],
    "javascript": [
        "Explain the difference between 'let', 'const', and 'var'.",
        "What is a closure in JavaScript, and can you give a practical example?",
        "How does the JavaScript event loop work?",
    ],
    "sql": [
        "What's the difference between INNER JOIN and LEFT JOIN?",
        "Explain database normalization and why it matters.",
        "How would you find duplicate rows in a table using SQL?",
    ],
    "react": [
        "What's the difference between state and props in React?",
        "Explain the purpose of the useEffect hook, with an example.",
        "How does React's virtual DOM improve performance?",
    ],
    "node.js": [
        "How does Node.js handle asynchronous operations?",
        "What's the difference between 'require' and 'import' in a Node.js project?",
        "Explain what middleware is in an Express application.",
    ],
    "django": [
        "Explain Django's MVT (Model-View-Template) architecture.",
        "What's the difference between Django's ORM 'select_related' and 'prefetch_related'?",
    ],
    "flask": [
        "How does routing work in Flask?",
        "What's the difference between Flask's app context and request context?",
    ],
    "docker": [
        "What's the difference between a Docker image and a Docker container?",
        "Explain what a Dockerfile does and name two common instructions in one.",
    ],
    "aws": [
        "What's the difference between EC2 and Lambda, and when would you choose each?",
        "Explain what an S3 bucket is used for.",
    ],
    "git": [
        "What's the difference between 'git merge' and 'git rebase'?",
        "How would you resolve a merge conflict?",
    ],
    "nmap": [
        "What's the difference between a TCP SYN scan and a TCP connect scan in Nmap?",
        "How would you use Nmap to identify the operating system of a target host?",
    ],
    "wireshark": [
        "How would you use Wireshark to identify a potential port scan on a network?",
        "What's the difference between a capture filter and a display filter in Wireshark?",
    ],
    "owasp": [
        "Can you name three items from the OWASP Top 10 and briefly explain one?",
        "What is SQL injection, and how would you defend against it?",
    ],
    "penetration testing": [
        "Walk through the typical phases of a penetration test.",
        "What's the difference between black-box, white-box, and grey-box testing?",
    ],
    "machine learning": [
        "What's the difference between supervised and unsupervised learning?",
        "Explain overfitting and one technique to reduce it.",
    ],
    "data structures and algorithms": [
        "What's the time complexity of binary search, and what precondition does it require?",
        "Explain the difference between a stack and a queue, with a real-world example of each.",
    ],
    "typescript": [
        "What does TypeScript add on top of JavaScript, and what problem does static typing solve for a team?",
        "What's the difference between an 'interface' and a 'type' in TypeScript?",
    ],
    "angular": [
        "What's the difference between a component and a service in Angular?",
        "Explain Angular's dependency injection system, at a high level.",
    ],
    "vue": [
        "What's the difference between a computed property and a watcher in Vue?",
        "Explain the purpose of the Composition API compared to the Options API.",
    ],
    "c++": [
        "What's the difference between a pointer and a reference in C++?",
        "Explain what RAII means and why it matters for resource management.",
    ],
    "c#": [
        "What's the difference between a value type and a reference type in C#?",
        "Explain what async/await does in C# and why it's useful.",
    ],
    "php": [
        "What's the difference between '==' and '===' in PHP?",
        "How does PHP handle sessions, at a high level?",
    ],
    "ruby": [
        "What's the difference between a block, a proc, and a lambda in Ruby?",
        "Explain what 'attr_accessor' does in a Ruby class.",
    ],
    "ruby on rails": [
        "Explain the MVC pattern as Rails implements it.",
        "What's the difference between 'has_many' and 'has_and_belongs_to_many' in Rails?",
    ],
    "go": [
        "What's the difference between a goroutine and an OS thread, at a high level?",
        "How does Go's channel-based concurrency model work?",
    ],
    "kotlin": [
        "What's the difference between 'val' and 'var' in Kotlin?",
        "How does Kotlin help avoid null pointer exceptions compared to Java?",
    ],
    "swift": [
        "What's the difference between a struct and a class in Swift?",
        "Explain how optionals work in Swift and why they exist.",
    ],
    "android": [
        "What's the difference between an Activity and a Fragment in Android?",
        "Explain the Android app lifecycle, at a high level.",
    ],
    "ios": [
        "What's the difference between a strong and a weak reference in iOS development?",
        "Explain the difference between UIKit and SwiftUI.",
    ],
    "azure": [
        "What's the difference between Azure App Service and an Azure VM, and when would you choose each?",
        "What is an Azure Resource Group used for?",
    ],
    "gcp": [
        "What's the difference between Google Cloud Run and Compute Engine, and when would you choose each?",
        "What is Google Cloud IAM used for?",
    ],
    "kubernetes": [
        "What's the difference between a Pod and a Deployment in Kubernetes?",
        "How does Kubernetes decide to restart or reschedule a failing container?",
    ],
    "mongodb": [
        "What's the difference between MongoDB and a relational database like PostgreSQL?",
        "Explain what an index does in MongoDB and why it matters for query performance.",
    ],
    "postgresql": [
        "What's the difference between a primary key and a unique constraint in PostgreSQL?",
        "Explain what a database transaction is and why ACID properties matter.",
    ],
    "mysql": [
        "What's the difference between InnoDB and MyISAM storage engines in MySQL?",
        "How would you optimize a slow-running MySQL query?",
    ],
    "redis": [
        "What is Redis typically used for in an application's architecture?",
        "What's the difference between Redis's caching use case and its use as a message broker?",
    ],
    "kafka": [
        "What's the difference between a Kafka topic and a partition?",
        "Explain what a consumer group does in Kafka.",
    ],
    "spring boot": [
        "What's the difference between '@Component', '@Service', and '@Repository' in Spring?",
        "Explain what Spring Boot auto-configuration does.",
    ],
    "rest api": [
        "What's the difference between PUT and PATCH in a REST API?",
        "What makes an API 'RESTful'? Name a couple of the key constraints.",
    ],
    "graphql": [
        "What's the difference between REST and GraphQL, and when would you choose each?",
        "What is over-fetching, and how does GraphQL address it?",
    ],
    "html": [
        "What's the difference between a block-level and an inline element in HTML?",
        "What's the purpose of semantic HTML tags like <article> or <section>?",
    ],
    "css": [
        "What's the difference between 'flexbox' and 'CSS grid', and when would you use each?",
        "Explain how CSS specificity is calculated.",
    ],
    "linux": [
        "How would you find which process is using a specific port on a Linux machine?",
        "What's the difference between a hard link and a symbolic link?",
    ],
    "networking": [
        "What's the difference between TCP and UDP?",
        "Explain what happens, step by step, during a DNS lookup.",
    ],
    "cloud security": [
        "What's the principle of least privilege, and how would you apply it to a cloud IAM setup?",
        "What's the difference between encryption at rest and encryption in transit?",
    ],
    "agile": [
        "What's the difference between Scrum and Kanban?",
        "What's the purpose of a sprint retrospective, and how do you make one actually useful?",
    ],
    "scrum": [
        "What are the main ceremonies in Scrum, and what's the purpose of each?",
        "How do you handle a sprint when priorities change halfway through?",
    ],
    "testing": [
        "What's the difference between unit testing and integration testing?",
        "How do you decide what's worth writing a test for versus what isn't?",
    ],
    "qa": [
        "What's the difference between manual and automated testing, and when would you use each?",
        "How would you write a test plan for a new feature with no existing documentation?",
    ],
    "ci/cd": [
        "What's the difference between continuous integration and continuous deployment?",
        "What would you check first if a CI pipeline that was passing suddenly starts failing?",
    ],
    "terraform": [
        "What problem does infrastructure as code solve that manual provisioning doesn't?",
        "What's the difference between 'terraform plan' and 'terraform apply'?",
    ],
    "excel": [
        "What's the difference between VLOOKUP and INDEX/MATCH, and why might you prefer one?",
        "How would you use a pivot table to summarize a large dataset?",
    ],
    "power bi": [
        "What's the difference between a measure and a calculated column in Power BI?",
        "How would you design a dashboard so a non-technical stakeholder can act on it quickly?",
    ],
    "tableau": [
        "What's the difference between a dimension and a measure in Tableau?",
        "How would you choose which chart type to use for a given dataset?",
    ],
    "deep learning": [
        "What's the difference between a CNN and an RNN, and what is each typically used for?",
        "What is backpropagation, at a high level?",
    ],
    "nlp": [
        "What's the difference between stemming and lemmatization?",
        "What is a word embedding, and why is it useful over one-hot encoding?",
    ],
}

# Aliases map common variants/synonyms recruiters and candidates actually type
# (e.g. "ReactJS", "Node", "Postgres") onto the canonical keys in the bank
# above, so a slightly different spelling doesn't silently fall through to
# the generic fallback questions.
SKILL_ALIASES = {
    "reactjs": "react", "react.js": "react",
    "node": "node.js", "nodejs": "node.js", "node js": "node.js",
    "vue.js": "vue", "vuejs": "vue",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "k8s": "kubernetes",
    "golang": "go",
    "c plus plus": "c++", "cpp": "c++",
    "csharp": "c#", ".net": "c#", "dotnet": "c#",
    "rails": "ruby on rails",
    "amazon web services": "aws",
    "google cloud": "gcp", "google cloud platform": "gcp",
    "microsoft azure": "azure",
    "spring": "spring boot",
    "rest": "rest api", "restful api": "rest api", "restful apis": "rest api",
    "html5": "html",
    "css3": "css",
    "pen testing": "penetration testing", "pentest": "penetration testing", "pentesting": "penetration testing",
    "ml": "machine learning",
    "dsa": "data structures and algorithms",
    "ci cd": "ci/cd", "cicd": "ci/cd", "continuous integration": "ci/cd",
    "qa testing": "qa", "software testing": "testing",
    "sre": "linux",
}

# Fallback questions keyed by keyword in the job title, used only when none
# of the job's listed skills match the bank (directly or via alias). This
# keeps the fallback at least role-aware instead of fully generic.
ROLE_FALLBACK_QUESTIONS = {
    "frontend": [
        "Walk me through how you'd approach making a web page load faster for users on a slow connection.",
        "How do you approach making a UI accessible to users relying on a screen reader?",
    ],
    "backend": [
        "How would you design an API endpoint that needs to handle a sudden spike in traffic?",
        "Walk me through how you'd debug a backend service that's returning intermittent 500 errors.",
    ],
    "full stack": [
        "Walk me through how a request flows from the browser to your database and back, in a project you've built.",
        "How do you decide whether a piece of logic belongs on the frontend or the backend?",
    ],
    "devops": [
        "Walk me through how you'd respond to a production outage from first alert to resolution.",
        "How do you approach rolling out a change safely without downtime?",
    ],
    "data": [
        "Walk me through how you'd validate that a dataset is reliable before building a model or report on top of it.",
        "How do you communicate a data finding to a non-technical stakeholder?",
    ],
    "security": [
        "Walk me through how you'd triage a report that a system may have been compromised.",
        "How do you balance security requirements against a team's need to ship quickly?",
    ],
    "mobile": [
        "How do you approach testing an app across a range of device sizes and OS versions?",
        "Walk me through how you'd debug a crash that only happens on certain devices.",
    ],
    "product": [
        "Walk me through how you'd prioritize a backlog when engineering, sales, and support all want different things.",
        "How do you decide when a feature is 'done enough' to ship?",
    ],
    "manager": [
        "Tell me about a time you had to give a teammate difficult feedback. How did you approach it?",
        "How do you decide what to delegate versus what to handle yourself?",
    ],
}

BEHAVIORAL_QUESTIONS = [
    "Tell me about a time you had to learn a new technology quickly for a project. How did you approach it?",
    "Describe a situation where you disagreed with a teammate's technical decision. How did you handle it?",
    "Tell me about a project you're proud of. What was your specific contribution?",
    "How do you prioritize when you have multiple deadlines at once?",
    "Describe a time something you built didn't work as expected. What did you do next?",
]

GENERIC_TECHNICAL_FALLBACK = [
    "Walk me through how you'd approach debugging an issue you've never seen before.",
    "Describe the architecture of a project you've built, and why you made the design choices you did.",
]


def _resolve_skill_key(skill):
    """Normalize a raw skill string to a bank key, trying an exact match
    first and then the alias table (e.g. 'ReactJS' -> 'react')."""
    skill_key = skill.lower().strip()
    if skill_key in TECHNICAL_QUESTION_BANK:
        return skill_key
    return SKILL_ALIASES.get(skill_key)


def generate_interview_questions(job_title, skills, max_technical=6, max_behavioral=3):
    """Returns {opening, technical: [{skill, question}, ...], behavioral: [...]}"""
    skills = skills or []
    technical = []
    seen_skills = set()

    for skill in skills:
        bank_key = _resolve_skill_key(skill)
        if not bank_key or bank_key in seen_skills:
            continue
        bank_questions = TECHNICAL_QUESTION_BANK.get(bank_key)
        if bank_questions:
            # Rotate which question from the bank is used so that two jobs
            # sharing a skill don't always show candidates the identical
            # first question -- still deterministic per skill+role.
            idx = abs(hash((job_title or "", bank_key))) % len(bank_questions)
            technical.append({"skill": skill, "question": bank_questions[idx]})
            seen_skills.add(bank_key)
        if len(technical) >= max_technical:
            break

    if not technical:
        title_lower = (job_title or "").lower()
        role_questions = None
        for keyword, questions in ROLE_FALLBACK_QUESTIONS.items():
            if keyword in title_lower:
                role_questions = questions
                break
        fallback = (role_questions or []) + GENERIC_TECHNICAL_FALLBACK
        technical = [{"skill": "General", "question": q} for q in fallback[:max_technical]]

    behavioral = BEHAVIORAL_QUESTIONS[:max_behavioral]

    opening = f"Tell me about yourself and why you're interested in this {job_title} role."

    return {
        "opening": opening,
        "technical": technical,
        "behavioral": behavioral,
    }
