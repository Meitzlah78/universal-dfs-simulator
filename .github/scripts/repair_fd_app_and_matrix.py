from pathlib import Path
import subprocess

# Restore dfs_app.py from the last known-good 50K commit, then fix the diagnostic matrix.
subprocess.run(['git','show','243422ae30775c0737e9e6fdb8257f67b2c82db9:dfs_app.py'], check=True, stdout=open('dfs_app.py','wb'))
p=Path('dfs_app.py')
s=p.read_text()
old='''                            _fd_all_user_matrix = _fd_matrix_indices(compared)\n                            if np.all(_fd_all_user_matrix >= 0):\n                                _fd_all_n = len(compared)'''
new='''                            _fd_all_user_matrix = _fd_matrix_indices(compared)\n                            _fd_diag_field_matrix = _fd_matrix_indices(opponent_df)\n                            if np.all(_fd_all_user_matrix >= 0) and np.all(_fd_diag_field_matrix >= 0):\n                                _fd_all_n = len(compared)'''
if old not in s: raise SystemExit('diagnostic anchor missing')
s=s.replace(old,new,1)
# Only the candidate-diagnostic loop should use the 10K diagnostic matrix.
marker='''                            # Evaluate every generated candidate independently against the SAME'''
pos=s.index(marker)
tail=s[pos:]
old2='_field_scores += _row[_fd_field_matrix[:, _slot_pos]] * _mult'
new2='_field_scores += _row[_fd_diag_field_matrix[:, _slot_pos]] * _mult'
if old2 not in tail: raise SystemExit('scoring anchor missing')
tail=tail.replace(old2,new2,1)
s=s[:pos]+tail
p.write_text(s)
print('restored app and separated 10K diagnostic matrix from 50K final matrix')