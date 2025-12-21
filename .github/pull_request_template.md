# Pull Request

## Summary

**What changed (concise):**
- 
- 
- 

**Why this change exists (user-visible or technical goal):**
- 

---

## Scope & Risk

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behavior change)
- [ ] Documentation
- [ ] Import / data pipeline
- [ ] Analytics / charts
- [ ] UI / UX

**Risk level (pick one):**
- [ ] Low (isolated change, easy rollback)
- [ ] Medium (touches core logic or UI paths)
- [ ] High (imports, schema, analytics, or cross-cutting behavior)

---

## How to Test

### Local (required)

Provide **exact commands** used to verify this change.

**Windows (PowerShell):**
```powershell
.\scripts\Setup.ps1
.\scripts\Start.ps1
# Open http://127.0.0.1:3001
# Test steps:
# 1. 
# 2. 
# 3. 
```

**Linux/macOS:**
```bash
pip install -r requirements.txt
python -m alembic upgrade head
python run.py
# Open http://127.0.0.1:3001
# Test steps:
# 1. 
# 2. 
# 3. 
```

**Android (Termux):**
```bash
./scripts/termux-setup.sh
./scripts/termux-run.sh
# Open http://127.0.0.1:3001 in Android browser
# Test steps:
# 1. 
# 2. 
# 3. 
```

### Automated Tests

**Run tests:**
```powershell
# Windows
.\scripts\Test.ps1

# Linux/macOS/Termux
python -m unittest discover -s tests -v
# or
pytest
```

**Test results:**
- [ ] All existing tests pass
- [ ] New tests added (if applicable)
- [ ] Test coverage: ___ (if measurable)

---

## Manual Verification Checklist

When changes affect UI or user workflows:

- [ ] App starts successfully using documented scripts
- [ ] Existing functionality still works (imports, analytics, navigation)
- [ ] Mobile view tested (360x800px in browser dev tools)
- [ ] Desktop view tested (1920x1080 or similar)
- [ ] Bottom nav behavior correct (visible on mobile, hidden on desktop)
- [ ] Charts load and drilldowns work (if applicable)
- [ ] Import workflows function correctly (GEDCOM/RMTree if applicable)
- [ ] No console errors in browser dev tools
- [ ] Responsive behavior verified across breakpoints

---

## Definition of Done

Confirm all criteria met:

- [ ] App starts successfully using the documented scripts
- [ ] Existing functionality still works (especially imports + analytics page)
- [ ] Tests run and pass
- [ ] New behavior is covered by tests OR has clear manual verification steps above
- [ ] No new heavyweight dependencies added
- [ ] No secrets or real family data committed
- [ ] UI changes are responsive (desktop + mobile)
- [ ] Code follows existing patterns and conventions
- [ ] Documentation updated (if needed)
- [ ] Changes are minimal and focused on the stated goal

---

## Screenshots / Evidence

<!-- If UI changes, include before/after screenshots -->
<!-- If CLI output, include relevant terminal output -->
<!-- If data/analytics, include sample output or charts -->

**Before:**


**After:**


---

## Additional Notes

<!-- Any caveats, follow-up work, or context reviewers should know -->
<!-- Known limitations or edge cases not addressed -->
<!-- Related issues or PRs -->
