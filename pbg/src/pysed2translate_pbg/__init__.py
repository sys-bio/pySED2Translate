"""pysed2translate-pbg: SED2 documents -> Process Bigraph composite documents.

Nothing outside this package knows about it (rule M1 of process-bigraph.md, section 3.11); this package reaches the host
only through `host.py` (rule M2).  Engines live in `engines/`, one folder each (rule M4).
"""
__version__ = "0.1.0"
