import unittest
from unittest.mock import patch
import simmah_runtime_release as release


class RoleReleaseTests(unittest.TestCase):
    def test_changed_helpers_reload_even_when_release_marker_is_reused(self):
        saved=(release._active_role_ownership_release,release._active_role_ownership_fingerprint)
        try:
            release._active_role_ownership_release=None
            release._active_role_ownership_fingerprint=None
            modules={name:object() for name in ('simmah_showdown_field','simmah_role_field_ownership','simmah_fantasylabs_ownership','simmah_rotowire',
                'simmah_projection_inputs','simmah_market_calibration','simmah_simulation_store')}
            with patch.dict(release.sys.modules,modules), patch.object(release.importlib,'reload') as reload:
                with patch.object(release.Path,'read_bytes',return_value=b'old'):
                    release.activate_role_ownership_release('same-marker')
                    self.assertEqual(reload.call_count,7)
                    release.activate_role_ownership_release('same-marker')
                    self.assertEqual(reload.call_count,7)
                with patch.object(release.Path,'read_bytes',return_value=b'fixed'):
                    release.activate_role_ownership_release('same-marker')
                    self.assertEqual(reload.call_count,14)
        finally:
            release._active_role_ownership_release,release._active_role_ownership_fingerprint=saved


if __name__=='__main__':unittest.main()
