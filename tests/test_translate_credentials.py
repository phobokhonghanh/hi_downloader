import os
import unittest
import threading
import concurrent.futures
from modules.translate.credentials import (
    GeminiCredentialStore,
    SecretServiceAdapter,
    SecretServiceUnavailableError,
)


class TestTranslateCredentials(unittest.TestCase):

    def setUp(self):
        # Save old environment variable state
        self._old_env_key = os.environ.get("GEMINI_API_KEY")
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
            
        # Use fake adapter for deterministic testing without dbus/secretstorage dependencies
        self.fake_adapter = SecretServiceAdapter(use_fake=True)
        self.store = GeminiCredentialStore(adapter=self.fake_adapter)

    def tearDown(self):
        # Restore environment variable
        if self._old_env_key is not None:
            os.environ["GEMINI_API_KEY"] = self._old_env_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

    def test_precedence_and_fallbacks(self):
        """Verify credential precedence order: session > secret_service > env."""
        # 1. Fallback to None when nothing is configured
        self.assertIsNone(self.store.resolve())

        # 2. Precedence Level 3: Environment Variable
        os.environ["GEMINI_API_KEY"] = "ENV_KEY_VAL_12345"
        self.assertEqual(self.store.resolve(), "ENV_KEY_VAL_12345")
        self.assertEqual(self.store.status()["source"], "environment")

        # 3. Precedence Level 2: OS Secret Service (persisted) overrides Env
        self.store.set("SECRET_KEY_VAL_67890", persist=True)
        self.assertEqual(self.store.resolve(), "SECRET_KEY_VAL_67890")
        self.assertEqual(self.store.status()["source"], "secret_service")

        # 4. Precedence Level 1: Session key overrides OS Secret Service
        self.store.set("SESSION_KEY_VAL_abcde", persist=False)
        self.assertEqual(self.store.resolve(), "SESSION_KEY_VAL_abcde")
        self.assertEqual(self.store.status()["source"], "session")

    def test_clear_credentials(self):
        """Test clearing credentials resets session and secret storage but keeps environment intact."""
        os.environ["GEMINI_API_KEY"] = "ENV_KEY"
        self.store.set("SECRET_KEY", persist=True)
        self.store.set("SESSION_KEY", persist=False)

        # Clear must remove session and secret_service keys
        self.store.clear()
        self.assertEqual(self.store.resolve(), "ENV_KEY")
        self.assertEqual(self.store.status()["source"], "environment")

    def test_api_key_masking(self):
        """Test credential masking hides full key in status hints and representation."""
        self.store.set("AIzaSyVerySecretAPIKey12345", persist=False)
        
        status = self.store.status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["hint"], "AIzaSy...2345")

        # Repr check must not leak the key
        self.assertNotIn("AIzaSyVerySecretAPIKey12345", repr(self.store))

    def test_unavailable_backend_errors(self):
        """Verify unavailable secret service raises typed error and doesn't leak secrets inside exception text."""
        # Force adapter to report unavailable state
        class UnavailableAdapter(SecretServiceAdapter):
            def is_available(self):
                return False

        bad_store = GeminiCredentialStore(adapter=UnavailableAdapter())
        secret_value = "AIzaSy_SecretKeyValue_MustNotLeak_9999"

        with self.assertRaises(SecretServiceUnavailableError) as context:
            bad_store.set(secret_value, persist=True)

        err_msg = str(context.exception)
        # Assert exception is typed correctly and does NOT contain the raw key
        self.assertNotIn(secret_value, err_msg)

    def test_concurrency_thread_safety(self):
        """Verify thread-safety by concurrently writing, reading and clearing credentials."""
        store = GeminiCredentialStore(adapter=SecretServiceAdapter(use_fake=True))

        def worker(i):
            key = f"KEY_THREAD_{i}"
            # Alternating operations
            if i % 3 == 0:
                store.set(key, persist=False)
            elif i % 3 == 1:
                store.resolve()
            else:
                store.clear()

        # Execute 50 threads concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, idx) for idx in range(1, 51)]
            for f in concurrent.futures.as_completed(futures):
                f.result()  # Should complete without deadlock or exceptions

    def test_clear_persistence_failure(self):
        """Verify store.clear raises SecretServiceUnavailableError on adapter delete failure but still clears session."""
        class FailingDeleteAdapter(SecretServiceAdapter):
            def __init__(self):
                super().__init__(use_fake=True)
            def delete_secret(self, key_name: str) -> None:
                raise SecretServiceUnavailableError("Mock deletion failure")

        failing_adapter = FailingDeleteAdapter()
        store = GeminiCredentialStore(adapter=failing_adapter)
        store.set("SESSION_KEY", persist=False)
        failing_adapter.save_secret("gemini_api_key", "SECRET_KEY")

        with self.assertRaises(SecretServiceUnavailableError):
            store.clear()

        # Session key must still be cleared
        self.assertIsNone(store._session_keys.get("gemini"))

    def test_provider_scoped_operations(self):
        """Test status, set, resolve, and reveal operations map correctly to specific providers."""
        # 1. Default fallback to gemini
        self.store.set("GEMINI_KEY_111", persist=False)
        self.assertEqual(self.store.resolve("gemini"), "GEMINI_KEY_111")
        self.assertEqual(self.store.reveal("gemini"), "GEMINI_KEY_111")
        
        # 2. Test status format contains all providers dictionary
        status = self.store.status("gemini")
        self.assertTrue(status["configured"])
        self.assertIn("providers", status)
        self.assertTrue(status["providers"]["gemini"]["configured"])
        
        # 3. Clear provider key
        self.store.clear("gemini")
        self.assertIsNone(self.store.resolve("gemini"))
        self.assertIsNone(self.store.reveal("gemini"))

    def test_reveal_only_user_stored_never_env(self):
        """Ensure reveal returns session/secret service keys but never environment variables."""
        os.environ["GEMINI_API_KEY"] = "ENV_KEY_XYZ"
        # Configured only via env
        self.assertEqual(self.store.resolve("gemini"), "ENV_KEY_XYZ")
        # Reveal must return None since no user key is set
        self.assertIsNone(self.store.reveal("gemini"))

        # Now set a session key
        self.store.set("USER_SESSION_KEY", persist=False)
        self.assertEqual(self.store.reveal("gemini"), "USER_SESSION_KEY")

    def test_environment_key_non_disclosure(self):
        """Confirm environment keys do not leak any character hint in credential status calls."""
        os.environ["GEMINI_API_KEY"] = "AIzaSy_ENV_SECRET_STAY_HIDDEN"
        status = self.store.status("gemini")
        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "environment")
        self.assertEqual(status["hint"], "", "Environment key hint must be empty to prevent leak")

    def test_unsupported_provider(self):
        """Verify that operations on unsupported providers raise ValueError or return None."""
        with self.assertRaises(ValueError):
            self.store.set("SOME_KEY", persist=False, provider="unsupported_provider")

        with self.assertRaises(ValueError):
            self.store.reveal("unsupported_provider")

        with self.assertRaises(ValueError):
            self.store.clear("unsupported_provider")

        self.assertIsNone(self.store.resolve("unsupported_provider"))
        
        # routes status checks
        with self.assertRaises(ValueError):
            self.store.status("unsupported_provider")

    def test_session_then_persisted_update(self):
        """Verify that persisting a key removes any active session overrides for that provider."""
        # 1. Set key in session
        self.store.set("SESSION_KEY_AAA", persist=False, provider="gemini")
        self.assertEqual(self.store.resolve("gemini"), "SESSION_KEY_AAA")
        self.assertEqual(self.store.status("gemini")["source"], "session")

        # 2. Persist a new key
        self.store.set("PERSISTED_KEY_BBB", persist=True, provider="gemini")
        # 3. Session key must be removed, resolve should return persisted key
        self.assertEqual(self.store.resolve("gemini"), "PERSISTED_KEY_BBB")
        self.assertEqual(self.store.status("gemini")["source"], "secret_service")
