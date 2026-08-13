import os
import time
import json
import shutil
import tempfile
import unittest
import threading
from typing import Dict, Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from modules.subtitle.schemas import SubtitleSegment
from modules.translate.providers.base import BaseTranslateProvider
from modules.translate.batch_service import TranslateBatchService
from modules.translate.credentials import GeminiCredentialStore, SecretServiceAdapter
from modules.translate.routes import (
    create_translate_router,
    CredentialsPutRequest,
    ScanFolderRequest,
    CreateBatchRequest,
    BatchActionRequest,
    SaveEditsRequest
)


class FakeSecretAdapter(SecretServiceAdapter):
    def __init__(self):
        super().__init__(use_fake=True)


class FakeTranslateProvider(BaseTranslateProvider):

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.last_token_usage = {
            "input_tokens": 50,
            "output_tokens": 30,
            "total_tokens": 80
        }

    def analyze_context(self, segments, config, cancel_event):
        return "Fake API test context summary"

    def translate_chunk(self, segments, config, context, cancel_event):
        prefix = f"[{config.target_language}] "
        return [
            SubtitleSegment(
                index=s.index,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text=f"{prefix}{s.text}",
                source="fake_provider"
            )
            for s in segments
        ]


class TestTranslateAPI(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

        self.adapter = FakeSecretAdapter()
        self.creds = GeminiCredentialStore(adapter=self.adapter)
        self.creds.set("MOCK_GEMINI_KEY_SECRET_STORE")

        self.cache = None
        self.batch_service = TranslateBatchService(
            provider_factory=lambda key: FakeTranslateProvider(api_key=key),
            credential_store=self.creds,
            cache=self.cache,
            max_workers_limit=2
        )
        self.addCleanup(self.batch_service.shutdown)

        self.opened_paths = []
        
        def open_cb(path: str):
            self.opened_paths.append(path)

        self.router = create_translate_router(
            batch_service=self.batch_service,
            credential_store=self.creds,
            provider_factory=lambda key: FakeTranslateProvider(api_key=key),
            open_location_cb=open_cb
        )

        # Helper to find route endpoints
        self.endpoints = {}
        for route in self.router.routes:
            # Normalize path and method mapping
            method = list(route.methods)[0] if route.methods else "GET"
            self.endpoints[(route.path, method)] = route.endpoint

        # Create dummy valid SRT files
        self.srt1 = os.path.join(self.temp_dir, "file1.srt")
        with open(self.srt1, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,100 --> 00:00:01,200\nHello\n")

        self.srt2 = os.path.join(self.temp_dir, "file2.srt")
        with open(self.srt2, "w", encoding="utf-8") as f:
            f.write("1\n00:00:02,100 --> 00:00:03,200\nWorld\n")

    def test_profiles(self):
        """Test GET /api/translate/profiles returns standard catalog data including explicit provider."""
        handler = self.endpoints[("/api/translate/profiles", "GET")]
        data = handler()
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["profile"], "economy")
        self.assertEqual(data[0]["provider"], "gemini")
        self.assertEqual(data[1]["profile"], "balanced")
        self.assertEqual(data[1]["provider"], "gemini")
        self.assertEqual(data[2]["profile"], "quality")
        self.assertEqual(data[2]["provider"], "gemini")

    def test_providers_catalog(self):
        """Test GET /api/translate/providers returns safe, non-disclosing provider catalog metadata."""
        handler = self.endpoints.get(("/api/translate/providers", "GET"))
        self.assertIsNotNone(handler, "GET /api/translate/providers endpoint is missing")
        
        data = handler()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "gemini")
        self.assertEqual(data[0]["name"], "Google Gemini")
        self.assertEqual(data[0]["env_var"], "GEMINI_API_KEY")
        
        # Verify secret_name or credentials keys are absolutely not leaked
        self.assertNotIn("secret_name", data[0])
        self.assertNotIn("gemini_api_key", str(data))

    def test_credentials_lifecycle(self):
        """Test credential management APIs."""
        get_handler = self.endpoints[("/api/translate/credentials", "GET")]
        put_handler = self.endpoints[("/api/translate/credentials", "PUT")]
        delete_handler = self.endpoints[("/api/translate/credentials", "DELETE")]

        # 1. GET Credentials configured status
        data = get_handler()
        self.assertTrue(data["configured"])
        self.assertNotIn("MOCK_GEMINI_KEY_SECRET_STORE", str(data))

        # 2. PUT set credential
        req = CredentialsPutRequest(api_key="NEW_KEY_VALUE", persist=False)
        res_put = put_handler(req)
        self.assertEqual(res_put["status"], "success")
        
        # Verify hint updated safely without showing credentials
        data2 = get_handler()
        self.assertTrue(data2["configured"])
        self.assertEqual(data2["source"], "session")
        self.assertNotIn("NEW_KEY_VALUE", str(data2))

        # 3. DELETE clear credentials
        res_del = delete_handler()
        self.assertEqual(res_del["status"], "success")
        
        data3 = get_handler()
        self.assertFalse(data3["configured"])

        # 4. DELETE clear credentials persistence failure mappings
        from modules.translate.credentials import SecretServiceUnavailableError
        
        class FailingAdapter:
            def is_available(self):
                return True
            def delete_secret(self, key_name: str) -> None:
                raise SecretServiceUnavailableError("Mock deletion failure")

        original_adapter = self.creds._adapter
        self.creds.set_adapter(FailingAdapter())
        
        with self.assertRaises(HTTPException) as ctx:
            delete_handler()
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("deletion failure", ctx.exception.detail)
        
        self.creds.set_adapter(original_adapter)

    def test_provider_scoped_credentials_api(self):
        """Test provider-aware API routing, reveal and non-disclosure rules."""
        get_provider_status = self.endpoints.get(("/api/translate/credentials/{provider}", "GET"))
        reveal_handler = self.endpoints.get(("/api/translate/credentials/{provider}/reveal", "GET"))
        put_provider = self.endpoints.get(("/api/translate/credentials/{provider}", "PUT"))
        delete_provider = self.endpoints.get(("/api/translate/credentials/{provider}", "DELETE"))

        # Fallback to base paths if not loaded via exact parameter path template
        if not get_provider_status:
            get_provider_status = self.endpoints.get(("/api/translate/credentials", "GET"))
            put_provider = self.endpoints.get(("/api/translate/credentials", "PUT"))
            delete_provider = self.endpoints.get(("/api/translate/credentials", "DELETE"))

        # 1. Test reveal key
        res_reveal = reveal_handler("gemini")
        self.assertEqual(res_reveal["api_key"], "MOCK_GEMINI_KEY_SECRET_STORE")

        # 2. Test reveal failure when only env key is configured
        self.creds.clear("gemini")
        os.environ["GEMINI_API_KEY"] = "ENV_KEY_VAL_1234"
        with self.assertRaises(HTTPException) as ctx:
            reveal_handler("gemini")
        self.assertEqual(ctx.exception.status_code, 404)

        # 3. Test environment key non-disclosure hint
        status = get_provider_status("gemini")
        self.assertEqual(status["hint"], "", "Hint must be empty to prevent disclosure of environment key")

        # Clean up env
        del os.environ["GEMINI_API_KEY"]

        # 4. PUT provider key
        req = CredentialsPutRequest(api_key="NEW_GEMINI_KEY", persist=False)
        res_put = put_provider(req, provider="gemini")
        self.assertEqual(res_put["status"], "success")
        self.assertEqual(self.creds.resolve("gemini"), "NEW_GEMINI_KEY")

        # 5. Unsupported provider errors
        with self.assertRaises(HTTPException) as ctx:
            get_provider_status("invalid_provider")
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx:
            reveal_handler("invalid_provider")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_test_credentials(self):
        """Test POST /api/translate/credentials/test resolves and tests keys safely."""
        test_handler = self.endpoints[("/api/translate/credentials/test", "POST")]
        delete_handler = self.endpoints[("/api/translate/credentials", "DELETE")]

        res = test_handler()
        self.assertEqual(res["status"], "success")

        # Clear credentials and retry
        delete_handler()
        with self.assertRaises(HTTPException) as ctx:
            test_handler()
        self.assertEqual(ctx.exception.status_code, 400)

    def test_scan_folder(self):
        """Test scan target directory endpoints, preserving lexical sorted direct child srt files."""
        scan_handler = self.endpoints[("/api/translate/scan-folder", "POST")]

        # Setup subfolder and extra files
        sub_dir = os.path.join(self.temp_dir, "nested")
        os.makedirs(sub_dir, exist_ok=True)
        
        nested_srt = os.path.join(sub_dir, "nested_file.srt")
        with open(nested_srt, "w") as f:
            f.write("nested content")

        txt_file = os.path.join(self.temp_dir, "normal.txt")
        with open(txt_file, "w") as f:
            f.write("text content")

        req = ScanFolderRequest(path=self.temp_dir)
        res = scan_handler(req)
        files = res["files"]
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0].endswith("file1.srt"))
        self.assertTrue(files[1].endswith("file2.srt"))

    def test_batches_apis_flow(self):
        """Test full translation batch flows, comparing, editing, and opening paths."""
        create_handler = self.endpoints[("/api/translate/batches", "POST")]
        get_batch_handler = self.endpoints[("/api/translate/batches/{batch_id}", "GET")]
        compare_handler = self.endpoints[("/api/translate/batches/{batch_id}/jobs/{job_id}/compare", "GET")]
        save_edits_handler = self.endpoints[("/api/translate/batches/{batch_id}/jobs/{job_id}/edits", "PUT")]
        open_loc_handler = self.endpoints[("/api/translate/batches/{batch_id}/jobs/{job_id}/open-location", "POST")]

        # 1. POST Create Batch
        payload = CreateBatchRequest(
            files=[self.srt1],
            target_language="vi",
            profile="balanced",
            concurrency=2
        )
        res = create_handler(payload)
        batch_id = res["batch_id"]

        # 2. GET Batch status checks
        self._wait_for_batch(batch_id)
        snap = get_batch_handler(batch_id)
        self.assertEqual(snap["status"], "done")
        self.assertEqual(snap["jobs"][0]["status"], "done")
        job_id = snap["jobs"][0]["job_id"]

        # Verify key is absent from batch snapshots
        self.assertNotIn("MOCK_GEMINI_KEY", str(snap))

        # 3. GET Compare Alignment
        comp_data = compare_handler(batch_id, job_id)
        self.assertEqual(comp_data["source_path"], self.srt1)
        self.assertTrue(comp_data["saved_path"].endswith("file1_vi.srt"))
        self.assertEqual(comp_data["segments"][0]["source_text"], "Hello")
        self.assertEqual(comp_data["segments"][0]["translated_text"], "[vi] Hello")

        # 4. PUT Save Edits
        edit_payload = SaveEditsRequest(edits={1: "Xin chào"})
        res_edit = save_edits_handler(batch_id, job_id, edit_payload)
        self.assertEqual(res_edit["status"], "success")

        # 5. POST Open Location
        res_open = open_loc_handler(batch_id, job_id)
        self.assertEqual(res_open["status"], "success")
        self.assertEqual(len(self.opened_paths), 1)
        self.assertTrue(self.opened_paths[0].endswith("file1_vi.srt"))

    def test_batches_action_trigger(self):
        """Test cancel and retry action commands dispatching and conflict checks."""
        create_handler = self.endpoints[("/api/translate/batches", "POST")]
        action_handler = self.endpoints[("/api/translate/batches/{batch_id}/action", "POST")]
        get_batch_handler = self.endpoints[("/api/translate/batches/{batch_id}", "GET")]

        # 1. Cancel action trigger
        payload = CreateBatchRequest(
            files=[self.srt1, self.srt2],
            target_language="vi",
            profile="balanced",
            concurrency=1
        )
        res = create_handler(payload)
        batch_id = res["batch_id"]

        # 409 conflict when unknown job_ids explicitly passed
        action_payload_invalid = BatchActionRequest(action="cancel", job_ids=["job-does-not-exist"])
        res_conflict = action_handler(batch_id, action_payload_invalid)
        self.assertEqual(res_conflict.status_code, 409)
        self.assertEqual(json.loads(res_conflict.body)["results"]["job-does-not-exist"]["outcome"], "missing")

        action_payload = BatchActionRequest(action="cancel", job_ids=[])
        res_act = action_handler(batch_id, action_payload)
        self.assertEqual(res_act["status"], "success")

        self._wait_for_batch(batch_id)
        snap = get_batch_handler(batch_id)
        self.assertEqual(snap["status"], "canceled")

        # 409 conflict when calling cancel on already canceled batch (no eligible jobs)
        res_no_eligible = action_handler(batch_id, action_payload)
        self.assertEqual(res_no_eligible.status_code, 409)

    def _wait_for_batch(self, batch_id: str, timeout: float = 3.0) -> None:
        start = time.time()
        while time.time() - start < timeout:
            snap = self.batch_service.get_batch(batch_id)
            if snap["status"] in ("done", "error", "canceled"):
                return
            time.sleep(0.02)
        self.fail("Timeout waiting for batch complete in API tests.")
