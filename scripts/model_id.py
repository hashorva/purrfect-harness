#!/usr/bin/env python3
"""Dependency-free model-id syntax and privacy validator shared by observation and ledger."""
import re

MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}\Z")
MODEL_SECRET_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"sk-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_",
    r"AKIA[0-9A-Z]{16}", r"xox[abpr]-", r"-----BEGIN", r"eyJ[A-Za-z0-9_-]{20,}\.",
    r"(?i:Bearer)\s+\S", r"[0-9A-Fa-f]{32,}", r"[A-Za-z0-9+/=]{40,}",
))
MODEL_ABSOLUTE_PATH = re.compile(r"/Users/|/private/|/var/folders/|/home/|[A-Za-z]:\\", re.I)
MODEL_SENSITIVE_PATH = re.compile(r"/tmp/|/etc/|(?<![\w.-])/(?:tmp|etc)\b|~[\w.-]*/|\$\{?HOME", re.I)
MODEL_UUID_SHAPE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")


def valid_model_id(value):
    if not isinstance(value, str) or "\n" in value or "\r" in value or not MODEL_ID_RE.fullmatch(value):
        return None
    if (MODEL_ABSOLUTE_PATH.search(value) or MODEL_SENSITIVE_PATH.search(value)
            or MODEL_UUID_SHAPE.search(value)
            or any(pattern.search(value) for pattern in MODEL_SECRET_PATTERNS)):
        return None
    return value
