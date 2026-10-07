"""BizzCheckup audit engine.

Pure Python: this package must never import Django, so it can be reused
outside the web app. Network work happens in collectors (crawler, fetcher);
checks only read the collected AuditContext.
"""
