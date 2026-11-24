#!/usr/bin/env python3
"""One command to put the skill to work in a project (environment check, Stop hook, .gitignore, stack report). See pdfmeasure/setup_project.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdfmeasure import setup_project  # noqa: E402

raise SystemExit(setup_project.main())
