# RecruitSmart Automated Test Suite

89 tests, all passing. Run from the project root:

```
pip install -r requirements.txt
pytest
```

## What's covered

| File | Covers |
|---|---|
| `test_models.py` | User password hashing, account lockout, role helpers, Resume JSON accessors |
| `test_matching.py` | TF-IDF + cosine-similarity resume-to-job matching engine (the ML component) |
| `test_authenticity.py` | Resume Authenticity Checker's 4 heuristics (timeline, content, duplicates, combined score) |
| `test_salary.py` | Rule-based salary predictor (experience/location/skill/GitHub multipliers) |
| `test_upload_security.py` | Magic-byte file-signature validation, malware/macro/zip-bomb/malicious-PDF scanning |
| `test_smoke.py` | App boots, public pages load, security headers present, register/login flow, access control |

Tests run against an in-memory SQLite database via the project's own
`testing` config (see `config.py`) — nothing here touches your real
`recruit_smart.db`, and no real Google/LinkedIn/Gmail credentials are
needed.

## Bug found and fixed while writing these tests

`app/utils/upload_security.py`: the "docx is a zip, don't flag its own PK
signature" exemption was accidentally written to skip **all** dangerous-
file checks (MZ/EXE, ELF, Mach-O, shell script) whenever the claimed
extension was `.docx` — not just the PK/zip check it was meant for. That
meant a Windows executable or shell script simply renamed to `resume.docx`
would have sailed straight through. Fixed so the docx exemption only
applies to the PK/zip signature; executables and scripts are still blocked
regardless of claimed extension. `test_elf_binary_disguised_as_docx_rejected`
covers this.
