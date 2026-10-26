"""Dependency-free public/reader contract identifiers for published summaries."""

SOURCE = "hkex_daily_summary"
RECORD_ID = r"hkex:daily:[0-9]{4}-[0-9]{2}-[0-9]{2}:[1-4]:[a-f0-9]{20}"
VERSION = r"hkex-daily-[a-f0-9]{32}"
NOTICE = "HKEX published daily-summary facts, not full filing documents, executed trades or current holdings. Summary date, relevant-event date and exact filing/publication time are different. Missing source dates remain unknown."
