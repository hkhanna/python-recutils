"""Encryption of confidential fields (manual chapter 13).

The rec format does not impose a specific encryption algorithm, but
requires that:

- The algorithm must be password-based.
- The value of any encrypted field begins with the string 'encrypted-'
  followed by the encrypted data.
- The encrypted data is encoded in some ASCII encoding such as base64.

This module uses a password-based SHA-256 keystream cipher with a random
salt.  A CRC-32 of the plaintext is stored inside the encrypted payload,
which makes it possible to detect whether a given password decrypts a
value: when the wrong password is supplied the encrypted data is left
as-is, as described in the manual.
"""

from __future__ import annotations

import base64
import hashlib
import os
import zlib

ENCRYPTED_PREFIX = "encrypted-"

_SALT_SIZE = 4


def is_encrypted(value: str) -> bool:
    """Check whether a field value holds encrypted data."""
    return value.startswith(ENCRYPTED_PREFIX)


def _keystream(password: str, salt: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    key = password.encode("utf-8")
    while len(out) < length:
        out += hashlib.sha256(key + salt + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(out[:length])


def encrypt_value(value: str, password: str) -> str:
    """Encrypt a field value with the given password."""
    plaintext = value.encode("utf-8")
    payload = plaintext + zlib.crc32(plaintext).to_bytes(4, "big")
    salt = os.urandom(_SALT_SIZE)
    stream = _keystream(password, salt, len(payload))
    ciphertext = bytes(a ^ b for a, b in zip(payload, stream))
    return ENCRYPTED_PREFIX + base64.b64encode(salt + ciphertext).decode("ascii")


def decrypt_value(value: str, password: str) -> str | None:
    """Decrypt a field value with the given password.

    Returns the plain text value, or None if the value is not encrypted
    data or the password is wrong.
    """
    if not is_encrypted(value):
        return None
    try:
        raw = base64.b64decode(value[len(ENCRYPTED_PREFIX) :], validate=True)
    except (ValueError, TypeError):
        return None
    if len(raw) < _SALT_SIZE + 4:
        return None
    salt, ciphertext = raw[:_SALT_SIZE], raw[_SALT_SIZE:]
    stream = _keystream(password, salt, len(ciphertext))
    payload = bytes(a ^ b for a, b in zip(ciphertext, stream))
    plaintext, checksum = payload[:-4], payload[-4:]
    if zlib.crc32(plaintext).to_bytes(4, "big") != checksum:
        return None
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError:
        return None
