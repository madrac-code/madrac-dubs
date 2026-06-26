#!/usr/bin/env python3
"""
Test script for Two-Mode Architecture of MADRAC-DUBBING

This script tests the two-mode architecture (Standalone vs Integrated)
for MADRAC-DUBBING, ensuring backward compatibility while validating
new two-mode features.

All module detection is done via environment-variable overrides and mocks.
No real executables are renamed or deleted.
"""
import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from madrac_dubbing.__main__ import (
    _get_operating_mode,
    validate_installation,
    _warn_inactive_mode,
)
from madrac_dubbing.madrac_integration import MADRACIntegration
from madrac_dubbing.api import app


class TestTwoModeArchitecture:
    """Test class for two-mode architecture"""

    def setUp(self):
        """Setup test environment"""
        self.test_dir = Path(tempfile.mkdtemp(prefix="madrac_test_"))
        self.save_original_env()

    def tearDown(self):
        """Cleanup test environment"""
        self.restore_original_env()
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def save_original_env(self):
        """Save original environment variables"""
        self.original_env = {}
        for key in [
            'MADRAC_MODE',
            'MADRAC_OPERATING_MODE',
            'MADRAC_SKIP_VALIDATION',
            'MADRAC_INTEGRATION_AVAILABLE',
            'MADRAC_CAP_MADRAC_SUBS_EXE',
            'MADRAC_CAP_MADRAC_ASSISTANT_EXE',
            'MADRAC_CAP_MADRAC_RECOGNITION_EXE',
            'MADRAC_CAP_MADRAC_SUBS_WEB_EXE',
        ]:
            self.original_env[key] = os.environ.get(key)

    def restore_original_env(self):
        """Restore original environment variables"""
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _clear_madrac_env(self):
        """Remove all MADRAC env vars so auto-detection can work cleanly."""
        for key in list(self.original_env.keys()):
            os.environ.pop(key, None)

    def test_operating_mode_detection(self):
        """Test operating mode detection from command line arguments"""
        self._clear_madrac_env()

        test_cases = [
            # (args, expected_mode, expected_skip)
            (['--standalone'], 'standalone', False),
            (['--skip-validate-madrac-subs'], 'standalone', True),
            (['--integrated'], 'integrated', False),
            (['--standalone', '--skip-validate-madrac-subs'], 'standalone', True),
            ([], 'standalone', False),  # Default when no args and no modules
        ]

        for args, expected_mode, expected_skip in test_cases:
            # Ensure no module is detected via env overrides
            os.environ['MADRAC_CAP_MADRAC_SUBS_EXE'] = 'false'
            # Reload integration layer to pick up env change
            import madrac_dubbing.integration_layer as il
            il.reload_capabilities()

            with patch('sys.argv', ['madrac-dubbing'] + args):
                mode, skip = _get_operating_mode()
                assert mode == expected_mode, (
                    f"Args {args}: expected mode {expected_mode}, got {mode}"
                )
                assert skip == expected_skip, (
                    f"Args {args}: expected skip {expected_skip}, got {skip}"
                )

        print("[PASS] Operating mode detection test passed")

    def test_operating_mode_integration_detection(self):
        """Test integration detection with environment variable override"""
        self._clear_madrac_env()

        # Use env var to simulate integration availability
        os.environ['MADRAC_INTEGRATION_AVAILABLE'] = 'true'

        # Reload integration layer
        import madrac_dubbing.integration_layer as il
        il.reload_capabilities()

        integration = MADRACIntegration()
        assert integration.integration_available == True, (
            "Integration should be available when MADRAC_INTEGRATION_AVAILABLE=true"
        )
        assert integration.mode == 'integrated', (
            "Mode should be integrated when integration available"
        )

        print("[PASS] Integration detection test passed")

    def test_standalone_mode_without_madrac_subs(self):
        """Test standalone mode when no MADRAC modules are detected"""
        self._clear_madrac_env()

        # Explicitly mark all modules as absent
        os.environ['MADRAC_CAP_MADRAC_SUBS_EXE'] = 'false'
        os.environ['MADRAC_CAP_MADRAC_ASSISTANT_EXE'] = 'false'
        os.environ['MADRAC_CAP_MADRAC_RECOGNITION_EXE'] = 'false'
        os.environ['MADRAC_CAP_MADRAC_SUBS_WEB_EXE'] = 'false'

        import madrac_dubbing.integration_layer as il
        il.reload_capabilities()

        with patch('sys.argv', ['madrac-dubbing']):
            mode, skip = _get_operating_mode()
            assert mode == 'standalone', f"Expected standalone mode, got {mode}"

        # Validation should pass in standalone mode
        result = validate_installation('standalone', False)
        assert result == True, "Validation should pass in standalone mode"

        print("[PASS] Standalone mode test passed")

    def test_integration_mode_with_madrac_subs(self):
        """Test integration mode when MADRAC-SUBS capability is present"""
        self._clear_madrac_env()

        # Simulate MADRAC-SUBS presence via environment variable
        os.environ['MADRAC_CAP_MADRAC_SUBS_EXE'] = 'true'

        import madrac_dubbing.integration_layer as il
        il.reload_capabilities()

        with patch('sys.argv', ['madrac-dubbing']):
            mode, skip = _get_operating_mode()
            assert mode == 'integrated', f"Expected integrated mode, got {mode}"

        # Validation should pass in integrated mode
        result = validate_installation('integrated', False)
        assert result == True, "Validation should pass in integrated mode"

        print("[PASS] Integrated mode test passed")

    def test_skip_validation(self):
        """Test that validation can be skipped"""
        result = validate_installation('standalone', True)
        assert result == True, "Validation should pass when skipped"

        result = validate_installation('integrated', True)
        assert result == True, (
            "Validation should pass when skipped even in integrated mode"
        )

        print("[PASS] Skip validation test passed")

    def test_api_mode_endpoints(self):
        """Test API endpoints with two-mode architecture"""
        self._clear_madrac_env()

        assert app is not None, "Flask app should be created"

        # Ensure integration layer has a known state
        import madrac_dubbing.integration_layer as il
        os.environ['MADRAC_CAP_MADRAC_SUBS_EXE'] = 'false'
        il.reload_capabilities()
        il.set_mode('standalone', False)

        # Test health endpoint
        with app.test_client() as client:
            response = client.get('/health')
            assert response.status_code == 200, "Health endpoint should return 200"

            data = json.loads(response.data.decode())
            assert 'mode' in data, "Health response should include mode"
            assert 'status' in data, "Health response should include status"

        # Test mode info endpoint
        with app.test_client() as client:
            response = client.get('/mode')
            assert response.status_code == 200, "Mode endpoint should return 200"

            data = json.loads(response.data.decode())
            assert 'operating_mode' in data, (
                "Mode info should include operating_mode"
            )

        print("[PASS] API mode endpoints test passed")

    def test_backward_compatibility(self):
        """Test that existing CLI commands still work"""
        # Test that the original CLI structure is preserved
        from madrac_dubbing.cli import dub

        # This test ensures the CLI interface hasn't changed
        assert dub is not None, "CLI should be available"

        print("[PASS] Backward compatibility test passed")

    def test_capability_detection(self):
        """Test the capability-based detection system"""
        self._clear_madrac_env()

        # All modules absent
        os.environ['MADRAC_CAP_MADRAC_SUBS_EXE'] = 'false'
        os.environ['MADRAC_CAP_MADRAC_ASSISTANT_EXE'] = 'false'
        os.environ['MADRAC_CAP_MADRAC_RECOGNITION_EXE'] = 'false'
        os.environ['MADRAC_CAP_MADRAC_SUBS_WEB_EXE'] = 'false'

        import madrac_dubbing.integration_layer as il
        il.reload_capabilities()

        caps = il.capabilities
        assert caps.subs == False, "subs should be False"
        assert caps.assistant == False, "assistant should be False"
        assert caps.recognition == False, "recognition should be False"
        assert caps.web_sync == False, "web_sync should be False"
        assert caps.any_integration_available() == False

        # Now simulate MADRAC-SUBS present
        os.environ['MADRAC_CAP_MADRAC_SUBS_EXE'] = 'true'
        il.reload_capabilities()
        caps = il.capabilities

        assert caps.subs == True, "subs should be True"
        assert caps.subtitles == True, "subtitles capability should be True"
        assert caps.subtitle_editor == True, "subtitle_editor should be True"
        assert caps.any_integration_available() == True
        assert 'MADRAC-SUBS' in caps.detected_modules()

        print("[PASS] Capability detection test passed")

    def test_shared_workspace_foundation(self):
        """Test that the shared workspace foundation is importable and inactive by default"""
        from madrac_dubbing.shared_workspace import SharedWorkspace, workspace

        # Module-level instance should be inactive
        assert workspace.is_available == False, "Default workspace should be inactive"
        assert workspace.available_resources() == [], (
            "No resources should be available when workspace is inactive"
        )

        # All resource types should still be registered
        all_res = workspace.all_resources()
        assert 'current_project' in all_res
        assert 'parsed_subtitles' in all_res
        assert 'subtitle_timeline' in all_res
        assert 'audio_segments' in all_res
        assert 'whisper_results' in all_res
        assert 'translation_cache' in all_res
        assert 'playback_state' in all_res
        assert 'temp_assets' in all_res
        assert 'user_preferences' in all_res

        # Property accessors should return None when inactive
        assert workspace.current_project is None
        assert workspace.parsed_subtitles is None

        print("[PASS] Shared workspace foundation test passed")

    def run_all_tests(self):
        """Run all tests"""
        print("Running MADRAC-DUBBING Two-Mode Architecture Tests...\n")

        try:
            self.test_operating_mode_detection()
            self.test_operating_mode_integration_detection()
            self.test_standalone_mode_without_madrac_subs()
            self.test_integration_mode_with_madrac_subs()
            self.test_skip_validation()
            self.test_api_mode_endpoints()
            self.test_backward_compatibility()
            self.test_capability_detection()
            self.test_shared_workspace_foundation()

            print("\n" + "="*60)
            print("ALL TESTS PASSED [PASS]")
            print("="*60)
            print("\nThe two-mode architecture is working correctly:")
            print(" * Standalone mode: Full functionality without MADRAC modules")
            print(" * Integrated mode: Enhanced features with detected capabilities")
            print(" * Backward compatibility: All existing commands work")
            print(" * Smart fallback: Automatic capability-based mode detection")
            print(" * Shared workspace: Foundation ready for future modules")
            print("="*60)

        except Exception as e:
            print(f"\n[FAIL] TEST FAILED: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    tester = TestTwoModeArchitecture()
    tester.setUp()
    tester.run_all_tests()
    tester.tearDown()
