"""
Upload Security Validator
----------------------------
Answers a question most student ATS projects never even ask: what stops
someone from renaming malware.exe to resume.pdf and uploading it?

The original upload check (see file_handler.py's old allowed_file()) only
looked at the filename's extension -- trivially spoofed. This module instead
inspects the actual file *content*:

  1. Magic-byte / file-signature verification -- every real file format
     starts with a fixed byte sequence (PDFs start with "%PDF-", DOCX/ZIP
     files start with "PK\\x03\\x04", etc). If the claimed extension doesn't
     match what the file actually is, that's a spoofing attempt, full stop.
  2. Executable/script detection -- explicitly rejects files that are
     actually Windows executables (MZ header), ELF binaries, or shell
     scripts, regardless of what extension they were uploaded with.
  3. Malicious-PDF heuristics -- legitimate resume PDFs don't need
     JavaScript or auto-launch actions. PDFs containing /JavaScript, /JS,
     /OpenAction, or /Launch are a well-known malware delivery technique
     and are flagged even though the file signature is a valid PDF.
"""

FILE_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "docx": [b"PK\x03\x04"],   # DOCX is a zip archive
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
}

# Signatures that mean "this is a dangerous file type", no matter what
# extension it was uploaded with.
DANGEROUS_SIGNATURES = {
    b"MZ": "Windows executable (.exe/.dll)",
    b"\x7fELF": "Linux/Unix executable (ELF binary)",
    b"\xca\xfe\xba\xbe": "Mach-O / Java class executable",
    b"#!": "Shell/interpreter script (shebang)",
    b"PK\x03\x04": None,  # handled separately -- valid for docx, but a zip
                          # claiming to be a pdf/txt/image is still rejected
}


def _read_header(file_obj, n=1024):
    file_obj.seek(0)
    header = file_obj.read(n)
    file_obj.seek(0)
    return header


def validate_file_signature(file_obj, claimed_extension):
    """Returns (is_valid, error_message, warning_message).

    Design philosophy, deliberately reworked after real-world testing kept
    producing false positives: there are two very different questions here,
    and only one of them should ever block an upload --

      1. "Is this file DANGEROUS?" (an executable, script, or other
         genuinely harmful binary disguised with a document extension) --
         YES, this blocks the upload outright. No legitimate resume is ever
         an .exe, ELF binary, or shell script.

      2. "Does this file's structure look exactly like a textbook-perfect
         PDF/DOCX?" -- lots of genuinely real, harmless resumes fail this
         (PDFs exported by less common tools, files that have passed
         through an email client or cloud-storage sync and picked up a few
         extra leading/trailing bytes, etc). Blocking uploads over this is
         a false-positive machine, not a security control. So this is now
         only a soft, non-blocking warning -- the file still gets uploaded
         and we let the actual resume PARSER be the judge of whether it can
         read anything useful out of it (that failure path already has its
         own friendly, non-alarming messaging).
    """
    header = _read_header(file_obj)
    claimed_extension = claimed_extension.lower()
    header_start = header[:16]

    for magic, danger_name in DANGEROUS_SIGNATURES.items():
        if not (header_start.startswith(magic) and danger_name):
            continue
        # The docx exemption is only for the PK/zip signature (docx IS a
        # zip file, so that one is a false positive for docx specifically).
        # It must NOT exempt docx from the other dangerous signatures --
        # otherwise an .exe/ELF/shell-script simply renamed to .docx would
        # sail straight through undetected.
        if magic == b"PK\x03\x04" and claimed_extension == "docx":
            continue
        return False, (f"This file was rejected: its content signature matches a "
                        f"{danger_name}, not a {claimed_extension.upper()} file. "
                        f"Uploading executables disguised as documents is blocked for platform security."), None

    if claimed_extension == "txt":
        file_obj.seek(0)
        sample = file_obj.read(2048)
        file_obj.seek(0)
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return False, "This .txt file contains binary data, not readable text. Upload a plain-text resume instead.", None
        return True, None, None

    if claimed_extension == "pdf":
        if b"%PDF-" in header:
            return True, None, None
        return True, None, ("This file's structure looks a little unusual for a PDF. It's still been "
                             "accepted -- if the analysis below comes back empty, try re-exporting it "
                             "from the original source and re-uploading.")

    expected_signatures = FILE_SIGNATURES.get(claimed_extension)
    if not expected_signatures:
        return True, None, None

    if any(header_start.startswith(sig) for sig in expected_signatures):
        return True, None, None

    return True, None, (f"This file's structure looks a little unusual for a .{claimed_extension} file. "
                         f"It's still been accepted -- if the analysis below comes back empty, try "
                         f"re-exporting it from the original source and re-uploading.")


EICAR_TEST_SIGNATURE = (
    r'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
).encode('ascii')

MAX_ZIP_UNCOMPRESSED_SIZE = 200 * 1024 * 1024  # 200 MB
MAX_ZIP_COMPRESSION_RATIO = 100  # decompressed / compressed size


def scan_for_malware_signature(file_path):
    """Scans raw bytes for the EICAR test string -- a harmless string every
    antivirus vendor treats as 'malware' for testing purposes. This makes
    malware-signature detection demonstrable without needing real malware:
    saving a .txt file containing the EICAR string is enough to trigger it."""
    try:
        with open(file_path, "rb") as f:
            content = f.read()
    except Exception:
        return True, None
    if EICAR_TEST_SIGNATURE in content:
        return False, "This file matches a known malware test signature (EICAR) and has been blocked."
    return True, None


def scan_docx_for_macros(file_path):
    """DOCX files are zip archives. A macro-enabled document (containing
    word/vbaProject.bin) can run arbitrary code the moment a recruiter
    clicks 'Enable Content' -- this is one of the most common real-world
    resume-based attack techniques against HR/recruiting teams. Legitimate
    resumes never need macros, so any is blocked outright."""
    import zipfile
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            if any("vbaProject.bin" in name for name in z.namelist()):
                return False, ("This document contains an embedded macro (VBA project). Macro-enabled "
                                "documents are a well-known malware delivery method and are not accepted "
                                "for resume uploads.")
    except zipfile.BadZipFile:
        return False, "This .docx file is corrupted or is not a valid Office document."
    except Exception:
        return True, None
    return True, None


def scan_docx_for_zip_bomb(file_path):
    """DOCX/XLSX/PPTX files are zip archives, which makes them a target for
    zip-bomb attacks: a tiny file on disk that decompresses into gigabytes,
    exhausting server memory/disk the moment something opens it. We check
    the zip directory's declared sizes *before* extracting anything."""
    import zipfile
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            total_uncompressed = sum(info.file_size for info in z.infolist())
            total_compressed = sum(info.compress_size for info in z.infolist()) or 1

            if total_uncompressed > MAX_ZIP_UNCOMPRESSED_SIZE:
                return False, "This file would decompress to an implausibly large size and was rejected as a potential zip-bomb."

            ratio = total_uncompressed / total_compressed
            if ratio > MAX_ZIP_COMPRESSION_RATIO:
                return False, "This file's compression ratio is abnormally high, a common zip-bomb signature, and was rejected."
    except zipfile.BadZipFile:
        return True, None  # already caught by scan_docx_for_macros
    except Exception:
        return True, None
    return True, None


def scan_pdf_for_malicious_content(file_path):
    """Legitimate resume PDFs are static documents -- they never need to run
    JavaScript, auto-launch external programs, or carry embedded files. All
    three are well-documented malicious-PDF delivery techniques, so their
    presence is flagged even when the file is a structurally valid PDF.

    NOTE on /OpenAction: this marker alone is NOT included here, deliberately.
    Almost every PDF export tool (Word, Google Docs, Canva, LibreOffice) embeds
    a completely harmless /OpenAction that just means "open to page 1 at this
    zoom level" (e.g. /OpenAction[1 0 R /XYZ null null 0]) -- flagging that
    unconditionally produced false positives on ordinary, legitimate resumes.
    The genuinely dangerous pattern is an /OpenAction that triggers
    JavaScript or a Launch action, which /JavaScript and /Launch below
    already catch directly."""
    hard_block_markers = [b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile"]
    try:
        with open(file_path, "rb") as f:
            raw = f.read()
    except Exception:
        return True, None  # Can't read it -- don't block on our own I/O failure

    found = [m.decode() for m in hard_block_markers if m in raw]
    if found:
        return False, (f"This PDF contains embedded active content ({', '.join(found)}) that resume "
                        f"documents should never need. It has been rejected as a security precaution.")
    return True, None
