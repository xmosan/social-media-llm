"""No production connection: exercise integrity checks with an in-memory object."""
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from botocore.response import StreamingBody
from scripts.verify_backup_restore import download_snapshot


class RestoreDownloadChecks(unittest.TestCase):
    def test_snapshot_checks_exact_get_bytes_and_legacy_checksum_uncertainty(self):
        data = b"synthetic compressed snapshot"
        config = {"S3_ACCESS_KEY": "fixture", "S3_SECRET_KEY": "fixture", "S3_BUCKET_NAME": "fixture",
                  "S3_ENDPOINT_URL": "https://storage.example.test"}
        client = Mock()
        now = datetime.now(timezone.utc)
        client.get_paginator.return_value.paginate.return_value = [{"Contents": [
            {"Key": "database_backups/backup_fixture.sql.gz", "LastModified": now}]}]
        for checksum, size, valid in ((hashlib.sha256(data).hexdigest(), len(data), True),
                                      (None, len(data), True), ("incorrect", len(data), False),
                                      (None, 0, False)):
            with self.subTest(checksum=checksum, size=size), tempfile.TemporaryDirectory() as directory:
                body = StreamingBody(io.BytesIO(data), len(data))
                client.get_object.return_value = {"Body": body, "ContentLength": size, "LastModified": now,
                                                  "Metadata": {"sha256": checksum} if checksum else {}}
                with patch("boto3.client", return_value=client):
                    if valid:
                        snapshot, report = download_snapshot(config, directory)
                        self.assertEqual(snapshot.read_bytes(), data)
                        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
                        self.assertEqual(report["checksum_verified"], bool(checksum))
                    else:
                        with self.assertRaises(RuntimeError):
                            download_snapshot(config, directory)
                self.assertTrue(body._raw_stream.closed)

    def test_missing_configuration_and_insecure_endpoint_fail_before_network(self):
        with patch("boto3.client") as client:
            for config in ({}, {"S3_ACCESS_KEY": "x", "S3_SECRET_KEY": "x", "S3_BUCKET_NAME": "x", "S3_ENDPOINT_URL": "http://example.test"}):
                with self.assertRaises(ValueError):
                    download_snapshot(config, Path("/unused"))
            client.assert_not_called()
