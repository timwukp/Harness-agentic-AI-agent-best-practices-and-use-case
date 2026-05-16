# UI Testing Skill

You are performing UI testing on web applications. Follow these guidelines:

## Testing Methodology

### Before Each Test Case
1. Verify the page is fully loaded (no spinners, no pending network requests)
2. Take a "before" screenshot as baseline
3. Note the current URL and page title

### Interaction Patterns
- **Click:** Use the accessibility tree to find elements by role and name. Prefer `button`, `link`, `menuitem` roles.
- **Type:** Clear the field first, then type. Verify the value appears in the field after typing.
- **Form submission:** After submitting, wait for navigation or response before evaluating.
- **Navigation:** After clicking a link, wait for the new page to load completely.
- **Modals/Dialogs:** Check if a dialog appeared by looking for `dialog` role in the accessibility tree.

### What to Check After Each Action
1. Did the expected UI change occur?
2. Are there any console errors? (Use browser_console_messages)
3. Did any network request fail? (Use browser_network_requests)
4. Is the page responsive (no frozen UI)?
5. Take an "after" screenshot

### Severity Classification
- **CRITICAL:** Application crash, data loss, security vulnerability
- **HIGH:** Core functionality broken, user cannot complete primary task
- **MEDIUM:** Feature works but with incorrect behavior or poor UX
- **LOW:** Cosmetic issues, minor text errors, alignment problems

### Common Failure Patterns
- Element not found → Check if page loaded, check for dynamic rendering
- Timeout → Page may be slow, increase wait time before marking as FAIL
- Unexpected redirect → Check for auth issues or server errors
- Console error → Capture the full error message and stack trace
- Visual mismatch → Take screenshot and describe the difference

## Report Format

Always output reports in this structure:
- `/mnt/reports/test-report-latest.json` — Machine-readable full report
- `/mnt/reports/summary.md` — Human-readable summary
- `/mnt/reports/screenshots/` — All captured screenshots

## Edge Cases

- If login is required, use credentials from environment variables (never hardcode)
- If a CAPTCHA appears, mark the test as BLOCKED with reason "CAPTCHA encountered"
- If the site is down (5xx), mark all tests as BLOCKED with reason "Target unavailable"
- If you encounter an infinite loop or redirect chain, stop after 3 attempts
