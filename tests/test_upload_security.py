"""Tests for app/utils/upload_security.py -- magic-byte verification,
dangerous-file detection, and PDF/DOCX-specific malware heuristics."""
import io
import os
import zipfile

import pytest

from app.utils.upload_security import (
    validate_file_signature,
    scan_for_malware_signature,
    scan_docx_for_macros,
    scan_docx_for_zip_bomb,
    scan_pdf_for_malicious_content,
    EICAR_TEST_SIGNATURE,
)


class TestValidateFileSignature:
    def test_valid_pdf_signature_accepted(self):
        f = io.BytesIO(b"%PDF-1.4\n%rest of a real pdf")
        is_valid, error, warning = validate_file_signature(f, "pdf")
        assert is_valid is True
        assert error is None

    def test_valid_docx_signature_accepted(self):
        f = io.BytesIO(b"PK\x03\x04" + b"rest of a zip-based docx")
        is_valid, error, warning = validate_file_signature(f, "docx")
        assert is_valid is True

    def test_exe_disguised_as_pdf_rejected(self):
        f = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00fake windows exe")
        is_valid, error, warning = validate_file_signature(f, "pdf")
        assert is_valid is False
        assert "executable" in error.lower()

    def test_elf_binary_disguised_as_docx_rejected(self):
        # docx is exempted from the generic PK check but not from the ELF check
        f = io.BytesIO(b"\x7fELF" + b"\x00" * 20)
        is_valid, error, warning = validate_file_signature(f, "docx")
        assert is_valid is False

    def test_shell_script_rejected(self):
        f = io.BytesIO(b"#!/bin/bash\nrm -rf /")
        is_valid, error, warning = validate_file_signature(f, "pdf")
        assert is_valid is False

    def test_odd_pdf_structure_gets_soft_warning_not_rejection(self):
        f = io.BytesIO(b"not really a pdf header but still text")
        is_valid, error, warning = validate_file_signature(f, "pdf")
        assert is_valid is True
        assert warning is not None

    def test_binary_txt_rejected(self):
        f = io.BytesIO(bytes([0x00, 0x01, 0xFF, 0xFE, 0x80]))
        is_valid, error, warning = validate_file_signature(f, "txt")
        assert is_valid is False

    def test_plain_text_txt_accepted(self):
        f = io.BytesIO(b"Just a plain text resume.")
        is_valid, error, warning = validate_file_signature(f, "txt")
        assert is_valid is True

    def test_valid_png_signature_accepted(self):
        f = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"restofpng")
        is_valid, error, warning = validate_file_signature(f, "png")
        assert is_valid is True

    def test_file_pointer_reset_after_check(self):
        f = io.BytesIO(b"%PDF-1.4\nrest")
        validate_file_signature(f, "pdf")
        assert f.tell() == 0


class TestScanForMalwareSignature:
    def test_clean_file_passes(self, tmp_path):
        path = tmp_path / "clean.txt"
        path.write_bytes(b"Just a normal resume with no malware signatures.")
        is_clean, error = scan_for_malware_signature(str(path))
        assert is_clean is True

    def test_eicar_signature_blocked(self, tmp_path):
        path = tmp_path / "eicar.txt"
        path.write_bytes(EICAR_TEST_SIGNATURE)
        is_clean, error = scan_for_malware_signature(str(path))
        assert is_clean is False
        assert "malware" in error.lower()

    def test_missing_file_does_not_crash(self, tmp_path):
        is_clean, error = scan_for_malware_signature(str(tmp_path / "does_not_exist.txt"))
        assert is_clean is True


class TestScanDocxForMacros:
    def _make_docx(self, tmp_path, names):
        path = tmp_path / "test.docx"
        with zipfile.ZipFile(path, "w") as z:
            for name in names:
                z.writestr(name, "content")
        return str(path)

    def test_docx_without_macros_passes(self, tmp_path):
        path = self._make_docx(tmp_path, ["word/document.xml", "[Content_Types].xml"])
        ok, error = scan_docx_for_macros(path)
        assert ok is True

    def test_docx_with_macro_blocked(self, tmp_path):
        path = self._make_docx(tmp_path, ["word/document.xml", "word/vbaProject.bin"])
        ok, error = scan_docx_for_macros(path)
        assert ok is False
        assert "macro" in error.lower()

    def test_corrupted_docx_blocked(self, tmp_path):
        path = tmp_path / "corrupt.docx"
        path.write_bytes(b"PK\x03\x04not actually a valid zip central directory")
        ok, error = scan_docx_for_macros(str(path))
        assert ok is False


class TestScanDocxForZipBomb:
    def test_normal_docx_passes(self, tmp_path):
        path = tmp_path / "normal.docx"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("word/document.xml", "Some normal document content here.")
        ok, error = scan_docx_for_zip_bomb(str(path))
        assert ok is True

    def test_high_compression_ratio_blocked(self, tmp_path):
        path = tmp_path / "bomb.docx"
        # Highly compressible content (all zeros) pushes the ratio over the
        # module's MAX_ZIP_COMPRESSION_RATIO threshold.
        huge_payload = b"0" * (50 * 1024 * 1024)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", huge_payload)
        ok, error = scan_docx_for_zip_bomb(str(path))
        assert ok is False


class TestScanPdfForMaliciousContent:
    def test_clean_pdf_passes(self, tmp_path):
        path = tmp_path / "clean.pdf"
        path.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF")
        ok, error = scan_pdf_for_malicious_content(str(path))
        assert ok is True

    def test_pdf_with_javascript_blocked(self, tmp_path):
        path = tmp_path / "malicious.pdf"
        path.write_bytes(b"%PDF-1.4\n/JavaScript (app.alert('hi'))\n%%EOF")
        ok, error = scan_pdf_for_malicious_content(str(path))
        assert ok is False
        assert "JavaScript" in error

    def test_pdf_with_launch_action_blocked(self, tmp_path):
        path = tmp_path / "launch.pdf"
        path.write_bytes(b"%PDF-1.4\n/Launch /F (cmd.exe)\n%%EOF")
        ok, error = scan_pdf_for_malicious_content(str(path))
        assert ok is False

    def test_pdf_with_harmless_openaction_not_blocked(self, tmp_path):
        # A plain "open to page 1" OpenAction with no JS/Launch must NOT be
        # flagged -- this is what almost every real PDF exporter emits.
        path = tmp_path / "harmless.pdf"
        path.write_bytes(b"%PDF-1.4\n/OpenAction[1 0 R /XYZ null null 0]\n%%EOF")
        ok, error = scan_pdf_for_malicious_content(str(path))
        assert ok is True
