== Plan ==
Summary: The fix for flag_value (issue #3084/#3130) exists in the main branch but was NOT included in the 8.3.1 release. The fix (commit 91de59c) was merged after the 8.3.1 tag was created. This is a release timing issue, not a code bug. The fix needs to be backported to stable and released in 8.3.2.
Steps:
  1. Verify fix is already in main/stable: The fix exists at commit 91de59c which changes src/click/core.py line 2784 from `self._flag_needs_value = self.default is UNSET` to `self._flag_needs_value = flag_value is not UNSET or self.default is UNSET`
  2. No code changes needed: The fix is complete and includes tests at tests/test_options.py:2292 (test_flag_value_on_option_with_zero_or_one_args)
  3. Release action required: A maintainer needs to create an 8.3.2 release that includes commit 91de59c and its cleanup commit 955ca49
  4. Validation: Users can verify the fix by testing with `--number` flag without argument - it should return flag_value (1) instead of requiring an argument
Risks:
  1. No code risks - fix is already merged and tested
  2. Users must wait for 8.3.2 release or use main branch directly
  3. Workaround: Users can pin to click from git main branch until 8.3.2 is released
Confidence: 0.95