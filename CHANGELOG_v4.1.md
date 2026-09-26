# RecruitSmart — v4.1 Changelog (Admin Security Hardening)

Applied on top of the v4 (Research Edition) codebase. No breaking changes
to existing routes, templates, or the data model beyond one new table and
one new column-level behavior change (2FA now actually enforced).

## What changed and why

The v4 Master Guide listed two items under Future Scope:
- "Admin action audit log"
- "Mandatory 2FA for admin accounts"

Both are now implemented. While wiring up mandatory 2FA, a real gap was
found and fixed in the existing code (see below) — worth mentioning
directly if an examiner asks "did you find any other bugs."

## 1. TOTP 2FA is now actually enforced (bug fix)

**What was there before:** `User.two_factor_enabled` / `two_factor_secret`
existed on the model, and `/auth/toggle-2fa` could flip `two_factor_enabled`
to `True` and generate a secret — but no route ever checked a TOTP code
against that secret. Enabling 2FA changed a stored flag with no actual
security effect at login.

**What's fixed:**
- `User.verify_totp(token)` — checks a code with a ±30s clock-drift window.
- Login is now two-step when `two_factor_enabled` is `True`: the password
  step parks a pending login in the session (`pending_2fa_user_id`) and
  redirects to `/auth/verify-2fa`, which only completes `login_user()`
  after a correct TOTP code. It never accepts a password itself, so it
  can't be used to skip the first factor.
- `/auth/setup-2fa` replaces the old instant-enable flow: it shows a QR
  code (rendered client-side via CDN `qrcodejs`, no new Python dependency)
  and the raw secret for manual entry, and only sets
  `two_factor_enabled = True` after the user proves they can generate a
  real code — so nobody can lock themselves out with an unscanned QR.

## 2. Mandatory 2FA for admin accounts

`admin_required` (in `app/utils/decorators.py`) now redirects any admin
without `two_factor_enabled` to `/auth/setup-2fa` before allowing access
to *any* admin route. `toggle_2fa` also blocks an admin from disabling 2FA
once it's on. Existing admin accounts created before this change are
enforced on their next request, not retroactively logged out mid-session.

## 3. Admin action audit log

New `AdminAuditLog` model (`app/models.py`), separate from the existing
general-purpose `ActivityLog`. Every privileged, state-changing admin
route now writes one row via a new `log_admin_action()` helper in
`app/admin/routes.py`:

| Route | Action logged |
|---|---|
| `POST /admin/user/<id>/toggle` | `user_activated` / `user_deactivated` |
| `POST /admin/user/<id>/unlock` | `user_unlocked` |
| `POST /admin/user/<id>/delete` | `user_deleted` |
| `POST /admin/recruiter/<id>/approve` | `recruiter_approved` |
| `POST /admin/recruiter/<id>/reject` | `recruiter_rejected` |
| `POST /admin/settings` | `platform_settings_updated` |

`actor_email` and `target_label` are denormalized (copied at write time)
so the log stays readable even after the actor's or target's account is
later renamed or deleted. The most recent 25 entries are shown in the
existing admin Security Center page (`/admin/security`).

## 4. New tests

`tests/test_admin_security.py` — 11 tests covering TOTP verification
(correct/incorrect/disabled/empty codes), the two-step 2FA login flow,
the mandatory-2FA redirect for admins, and audit log writes on a real
admin action.

**Not verified in this environment:** this was written and edited in a
sandbox with no internet access, so `pip install -r requirements.txt` and
`pytest -q` could not actually be run here. Every file passed a Python
syntax/AST check, and the logic was traced carefully against the existing
codebase's own patterns (session handling, `log_activity`, decorator
style) — but run `pytest -q` yourself before your review to get the real
pass count. If the whole suite doesn't run clean, the audit log rows
depend on order of operations; that's the section most worth a fresh eye.

## 5. SBERT baseline (not added)

The `research/matching_lib.py` `sbert_score()` hook was already correctly
wired in v4 (imports `sentence-transformers` lazily, returns `None` and
is skipped cleanly if it's not installed). It was **not** possible to
actually install and run it here — no internet access in this sandbox,
and `sentence-transformers` pulls in `torch`, which isn't cached locally.
To enable it yourself: `pip install sentence-transformers` on a machine
with internet, then re-run `research/baseline_comparison.py` — no code
changes needed.
