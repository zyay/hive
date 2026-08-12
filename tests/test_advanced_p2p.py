"""Tests for NAT traversal, E2EE files, QR pairing, and CLI chat."""

import pytest
import time
import json
import os
import tempfile
from pathlib import Path


class TestNATTraversal:
    def test_nat_info_creation(self):
        from hive.core.nat_traversal import NATInfo
        info = NATInfo(
            nat_type="open",
            internal_ip="192.168.1.5",
            internal_port=4242,
            external_ip="1.2.3.4",
            external_port=4242,
        )
        d = info.to_dict()
        assert d["nat_type"] == "open"
        assert d["external_ip"] == "1.2.3.4"

    def test_generate_connection_offer(self):
        from hive.core.nat_traversal import NATInfo, generate_connection_offer
        info = NATInfo("restricted", "192.168.1.5", 4242, "1.2.3.4", 5555)
        offer = generate_connection_offer(info, "hive:test123", "TestUser")
        assert offer["did"] == "hive:test123"
        assert offer["name"] == "TestUser"
        assert offer["external_ip"] == "1.2.3.4"

    def test_encode_decode_offer(self):
        from hive.core.nat_traversal import encode_offer, decode_offer
        offer = {"did": "hive:abc", "ip": "1.2.3.4", "port": 4242}
        encoded = encode_offer(offer)
        decoded = decode_offer(encoded)
        assert decoded["did"] == "hive:abc"
        assert decoded["ip"] == "1.2.3.4"

    def test_get_local_ip(self):
        from hive.core.nat_traversal import _get_local_ip
        ip = _get_local_ip()
        assert ip  # Should return some IP


class TestE2EEFiles:
    def test_encrypt_decrypt_file(self, tmp_path):
        from hive.core.e2ee_files import encrypt_file, decrypt_file, FileMetadata

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello E2EE World! " * 100)

        # Encrypt
        metadata, chunks = encrypt_file(str(test_file), "hive:sender")
        assert metadata.filename == "test.txt"
        assert metadata.chunk_count >= 1
        assert len(chunks) == metadata.chunk_count

        # Decrypt
        output = decrypt_file(metadata, chunks, str(tmp_path))
        assert output.exists()
        assert output.read_text() == "Hello E2EE World! " * 100

    def test_encrypt_large_file(self, tmp_path):
        from hive.core.e2ee_files import encrypt_file, decrypt_file

        # Create 200KB file (multiple chunks)
        test_file = tmp_path / "large.bin"
        test_file.write_bytes(os.urandom(200 * 1024))

        metadata, chunks = encrypt_file(str(test_file), "hive:sender")
        assert metadata.chunk_count >= 3  # 200KB / 64KB = ~3 chunks

        output = decrypt_file(metadata, chunks, str(tmp_path))
        assert output.read_bytes() == test_file.read_bytes()

    def test_file_hash_verification(self, tmp_path):
        from hive.core.e2ee_files import encrypt_file, decrypt_file

        test_file = tmp_path / "verify.txt"
        test_file.write_text("Verify me")

        metadata, chunks = encrypt_file(str(test_file), "hive:sender")
        assert len(metadata.sha256) == 64  # SHA-256 hex

    def test_file_transfer_manager(self, tmp_path):
        from hive.core.e2ee_files import FileTransferManager

        test_file = tmp_path / "transfer.txt"
        test_file.write_text("Transfer test data")

        mgr = FileTransferManager()
        metadata, chunks = mgr.start_send(str(test_file), "hive:sender")
        assert metadata.id in mgr._sending

        progress = mgr.get_progress(metadata.id)
        assert progress["direction"] == "send"
        assert progress["total"] == metadata.chunk_count


class TestQRPairing:
    def test_generate_invite_data(self):
        from hive.core.qr_pairing import generate_invite_data
        data = generate_invite_data(
            "hive:abc123", "TestUser", "signing_key_hex", "encryption_key_hex",
            ip="192.168.1.5", port=4242,
        )
        assert data["did"] == "hive:abc123"
        assert data["name"] == "TestUser"
        assert data["v"] == 1

    def test_format_safety_number(self):
        from hive.core.qr_pairing import format_safety_number
        fp = "abcde fghij klmno pqrst uvwxy"
        formatted = format_safety_number(fp)
        assert "abcde" in formatted

    def test_verify_safety_number_match(self):
        from hive.core.qr_pairing import verify_safety_number
        assert verify_safety_number("abc def", "abc def") is True
        assert verify_safety_number("ABC DEF", "abc def") is True

    def test_verify_safety_number_mismatch(self):
        from hive.core.qr_pairing import verify_safety_number
        assert verify_safety_number("abc def", "xyz 123") is False

    def test_generate_invite_qr_fallback(self):
        from hive.core.qr_pairing import generate_invite_qr
        data = {"did": "hive:test", "name": "Test"}
        qr = generate_invite_qr(data)
        assert len(qr) > 0  # Should return something (QR or fallback text)


class TestCLIChat:
    def test_cli_chat_import(self):
        try:
            from cli_chat import CLIChat
            chat = CLIChat()
            assert chat.identity is None
            assert chat.network is None
        except ImportError:
            pytest.skip("cli_chat not in path (CI environment)")
