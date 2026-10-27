"""
Guard: all user-facing text must be English.

Scans string literals (via `ast`, so comments and identifiers are ignored) in app/ and main.py
for common Indonesian words. Docstrings are skipped. If a literal legitimately contains one of
these words (e.g. a foreign-language sample), add it to ALLOWED_LITERALS.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Distinctive Indonesian words that are not English words (avoid ambiguous ones like "data", "di", "ini").
INDONESIAN_WORDS = {
    "belum", "gagal", "berhasil", "simpan", "disimpan", "menyimpan", "hapus", "dihapus", "menghapus",
    "batal", "dibatalkan", "tutup", "buka", "keluar", "akun", "pengaturan", "pilih", "kesalahan",
    "silakan", "apakah", "yakin", "sedang", "sudah", "tidak", "dengan", "untuk", "atau", "yang",
    "dari", "ubah", "tambah", "kosong", "lanjut", "lanjutan", "ulangi", "coba", "jaringan",
    "sinkron", "sinkronisasi", "menyinkronkan", "tersinkron", "disinkronkan", "salah", "sandi",
    "pengguna", "tersimpan", "memuat", "mengirim", "terhubung", "koneksi", "lokal", "perlu",
    "wajib", "mohon", "tunggu", "sebentar", "lagi", "sesi", "berakhir", "terlalu", "banyak",
    "permintaan", "diperbarui", "dilewati", "diterima", "dikirim", "perangkat", "masuk",
    "profil", "pindah", "detik", "menit", "jam", "hari", "lalu", "baru", "saja", "pernah",
    "ada", "dan", "tak", "terduga", "memproses", "ditolak", "bermasalah", "periksa", "otomatis",
}

# (relative path, literal text) pairs that are allowed to contain an Indonesian word.
ALLOWED_LITERALS: set[tuple[str, str]] = set()


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _offenders() -> list[str]:
    files = sorted((ROOT / "app").rglob("*.py")) + [ROOT / "main.py"]
    found = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstring_nodes(tree)
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in skip:
                continue
            if (rel, node.value) in ALLOWED_LITERALS:
                continue
            hits = set(re.findall(r"[a-z]+", node.value.lower())) & INDONESIAN_WORDS
            if hits:
                found.append(f"{rel}:{node.lineno}: {sorted(hits)} in {node.value[:80]!r}")
    return found


def test_ui_strings_are_english():
    offenders = _offenders()
    assert not offenders, "Indonesian text found in UI string literals:\n" + "\n".join(offenders)
