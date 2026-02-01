== Plan ==
Summary: CANARY123 - Custom CookiePolicy set on Session.cookies is discarded during prepare_request because a new RequestsCookieJar() with default policy is created instead of copying the session's jar with its policy. The fix uses _copy_cookie_jar to preserve the policy during cookie merging.
Steps:
  1. Edit src/requests/sessions.py imports (line 19-24): Add _copy_cookie_jar to the imports from .cookies
  2. Edit src/requests/sessions.py prepare_request method (lines 474-477): Replace `merge_cookies(merge_cookies(RequestsCookieJar(), self.cookies), cookies)` with `session_cookies = _copy_cookie_jar(self.cookies)` followed by `merged_cookies = merge_cookies(session_cookies, cookies)`
  3. Add test in tests/test_requests.py: Create test_custom_cookie_policy_persistence that sets a custom CookiePolicy on session.cookies, makes a request, and verifies the policy was consulted (similar to PR #4042's test)
  4. Validate by running the reproduction script from the issue to confirm 'Custom cookie policy got to examine this request' prints
  5. Run existing test suite (pytest tests/) to ensure no regressions
Risks:
  1. Generic CookieJar subclasses (not RequestsCookieJar) may not preserve policy correctly via _copy_cookie_jar - but _copy_cookie_jar already handles this by using copy.copy() which should preserve _policy attribute
  2. Edge case: if self.cookies is None, _copy_cookie_jar returns None which would break merge_cookies - but Session.__init__ always sets self.cookies to a valid jar
Confidence: 0.95