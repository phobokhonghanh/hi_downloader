import os
import threading
from typing import Optional, Dict, Any
from modules.translate.providers.models import TRANSLATION_PROVIDERS


class SecretServiceUnavailableError(Exception):
    """Exception raised when OS Secret Service is requested but unavailable."""
    pass


class SecretServiceAdapter:

    def __init__(self, use_fake: bool = False):
        self.use_fake = use_fake
        self._fake_store: Dict[str, str] = {}

    def is_available(self) -> bool:
        if self.use_fake:
            return True
        try:
            import secretstorage
            # Check dbus connectivity
            connection = secretstorage.dbus_init()
            secretstorage.get_default_collection(connection)
            return True
        except Exception:
            return False

    def save_secret(self, key_name: str, secret: str) -> None:
        if self.use_fake:
            self._fake_store[key_name] = secret
            return

        try:
            import secretstorage
            connection = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(connection)
            
            # Remove any stale items first
            self.delete_secret(key_name)
            
            collection.create_item(
                label=f"hi_downloader_{key_name}",
                attributes={"application": "hi_downloader", "key_name": key_name},
                secret=secret.encode("utf-8")
            )
        except Exception as e:
            # Ensure no secret content leaks in raw exception text
            err_msg = str(e)
            if secret in err_msg:
                err_msg = err_msg.replace(secret, "[REDACTED]")
            raise SecretServiceUnavailableError(f"OS Secret Service error: {err_msg}")

    def get_secret(self, key_name: str) -> Optional[str]:
        if self.use_fake:
            return self._fake_store.get(key_name)

        try:
            import secretstorage
            connection = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(connection)
            items = collection.search_items({"application": "hi_downloader", "key_name": key_name})
            for item in items:
                secret_bytes = item.get_secret()
                if secret_bytes:
                    return secret_bytes.decode("utf-8")
        except Exception:
            pass
        return None

    def delete_secret(self, key_name: str) -> None:
        if self.use_fake:
            if key_name not in self._fake_store:
                return  # Idempotent or noop
            self._fake_store.pop(key_name, None)
            return

        try:
            import secretstorage
            connection = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(connection)
            items = collection.search_items({"application": "hi_downloader", "key_name": key_name})
            for item in items:
                item.delete()
        except Exception as e:
            raise SecretServiceUnavailableError(f"OS Secret Service deletion error: {str(e)}")


class GeminiCredentialStore:

    def __init__(self, adapter: Optional[SecretServiceAdapter] = None):
        self._lock = threading.RLock()
        self._session_keys: Dict[str, str] = {}
        self._adapter = adapter or SecretServiceAdapter()

    def set_adapter(self, adapter: SecretServiceAdapter) -> None:
        with self._lock:
            self._adapter = adapter

    def set(self, key: str, persist: bool = False, provider: str = "gemini") -> None:
        if not key or not isinstance(key, str) or not key.strip():
            raise ValueError("Khoá API không được để trống.")

        clean_key = key.strip()

        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            raise ValueError(f"Provider '{provider}' không được hỗ trợ.")

        provider_config = next(p for p in TRANSLATION_PROVIDERS if p["id"] == provider)
        secret_name = provider_config["secret_name"]

        with self._lock:
            if persist:
                if not self._adapter.is_available():
                    raise SecretServiceUnavailableError(
                        "Không thể lưu trữ khoá lâu dài: OS Secret Service không khả dụng trên hệ thống này."
                    )
                try:
                    self._adapter.save_secret(secret_name, clean_key)
                    self._session_keys.pop(provider, None)
                except Exception as e:
                    err_msg = str(e)
                    if clean_key in err_msg:
                        err_msg = err_msg.replace(clean_key, "[REDACTED]")
                    raise SecretServiceUnavailableError(f"Không thể lưu khoá vào Secret Service: {err_msg}")
            else:
                self._session_keys[provider] = clean_key

    def resolve(self, provider: str = "gemini") -> Optional[str]:
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            return None

        provider_config = next(p for p in TRANSLATION_PROVIDERS if p["id"] == provider)
        secret_name = provider_config["secret_name"]
        env_var = provider_config["env_var"]

        with self._lock:
            if provider in self._session_keys:
                return self._session_keys[provider]

            if self._adapter.is_available():
                secret = self._adapter.get_secret(secret_name)
                if secret:
                    return secret

            env_val = os.environ.get(env_var)
            if env_val and env_val.strip():
                return env_val.strip()

            return None

    def get(self, provider: str = "gemini") -> Optional[str]:
        """Alias for resolve."""
        return self.resolve(provider)

    def reveal(self, provider: str = "gemini") -> Optional[str]:
        """Reveal only user-stored key (session or secret service). Never expose environment variables."""
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            raise ValueError(f"Provider '{provider}' không được hỗ trợ.")

        provider_config = next(p for p in TRANSLATION_PROVIDERS if p["id"] == provider)
        secret_name = provider_config["secret_name"]

        with self._lock:
            if provider in self._session_keys:
                return self._session_keys[provider]

            if self._adapter.is_available():
                secret = self._adapter.get_secret(secret_name)
                if secret:
                    return secret

            return None

    def clear(self, provider: str = "gemini") -> None:
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            raise ValueError(f"Provider '{provider}' không được hỗ trợ.")

        provider_config = next(p for p in TRANSLATION_PROVIDERS if p["id"] == provider)
        secret_name = provider_config["secret_name"]

        with self._lock:
            self._session_keys.pop(provider, None)
            if self._adapter.is_available():
                try:
                    self._adapter.delete_secret(secret_name)
                except Exception as e:
                    raise SecretServiceUnavailableError(f"Xóa lưu trữ lâu dài thất bại: {str(e)}")

    def status(self, provider: str = "gemini") -> Dict[str, Any]:
        supported = [p["id"] for p in TRANSLATION_PROVIDERS]
        if provider not in supported:
            raise ValueError(f"Provider '{provider}' không được hỗ trợ.")

        with self._lock:
            all_statuses = {}
            for p in TRANSLATION_PROVIDERS:
                p_id = p["id"]
                p_secret = p["secret_name"]
                p_env = p["env_var"]

                resolved = self.resolve(p_id)
                if not resolved:
                    all_statuses[p_id] = {
                        "configured": False,
                        "source": "none",
                        "hint": ""
                    }
                else:
                    if self._session_keys.get(p_id) == resolved:
                        source = "session"
                    elif self._adapter.is_available() and self._adapter.get_secret(p_secret) == resolved:
                        source = "secret_service"
                    elif os.environ.get(p_env) == resolved:
                        source = "environment"
                    else:
                        source = "unknown"

                    if source == "environment":
                        hint = ""
                    elif len(resolved) > 10:
                        hint = f"{resolved[:6]}...{resolved[-4:]}"
                    else:
                        hint = f"{resolved[:2]}...masked"

                    all_statuses[p_id] = {
                        "configured": True,
                        "source": source,
                        "hint": hint
                    }

            base_status = all_statuses.get(provider, {
                "configured": False,
                "source": "none",
                "hint": ""
            }).copy()

            base_status["providers"] = all_statuses
            return base_status

    def __repr__(self) -> str:
        return f"<GeminiCredentialStore configured={self.status()['configured']}>"
