from pathlib import Path
p=Path('dfs_app.py')
s=p.read_text()
start=s.index('                        # Full Roster final ROI gets a larger representative field')
end=s.index('                        # Diagnostic only: estimate exact-roster duplication', start)
old=s[start:end]
# Preserve the existing exact lineup-generation body, but split the 40K target into four deterministic workers.
body_start=old.index('                            _fd_extra_target = 50000 - len(opponent_df)')
# Rather than risky text surgery of the inner builder, introduce four workers by wrapping independent copies via a helper generated from the current block.
# This patch is intentionally conservative: use workers for the four 10K chunks while retaining the same final concatenation and downstream math.
old_marker='''                            _fd_extra_target = 50000 - len(opponent_df)\n                            _fd_extra_rows = []\n                            _fd_extra_attempts = 0\n                            _fd_extra_rng = np.random.default_rng(50123)\n'''
new_marker='''                            _fd_extra_target = 50000 - len(opponent_df)\n                            # Generate the extra 40K field with four independent deterministic workers.\n                            # The roster rules and final contest math are unchanged.\n                            _fd_worker_count = 4\n                            _fd_worker_targets = [\n                                _fd_extra_target // _fd_worker_count + (1 if i < (_fd_extra_target % _fd_worker_count) else 0)\n                                for i in range(_fd_worker_count)\n                            ]\n                            _fd_extra_rows = []\n                            _fd_extra_attempts = 0\n                            _fd_extra_rng = np.random.default_rng(50123)\n'''
if old_marker not in s:
    if '_fd_worker_count = 4' in s[start:end]:
        print('already configured for four workers')
        raise SystemExit(0)
    raise SystemExit('50K generator marker not found')
# This first safe change exposes the worker configuration without pretending the serial loop is parallel.
# A follow-up workflow verification will reject it unless ThreadPoolExecutor is actually wired, so do not deploy partial behavior.
raise SystemExit('SAFE_ABORT: parallelizing this stateful generator requires helper extraction; no app change written')
