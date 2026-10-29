"""Backward compatibility: Phase 3B must not change the original starter dataset in any way."""
from src.exports.checksums import telemetry_checksum

ORIGINAL_STARTER_MD5 = "c92c47e53d53369e131f07a37e026594"   # recorded during the original development


def test_starter_telemetry_checksum_is_the_original_one(engine, loaded):
    assert telemetry_checksum(engine) == ORIGINAL_STARTER_MD5
