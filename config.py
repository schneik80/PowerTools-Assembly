# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core
import os
import os.path
import json
from .lib import fusionAddInUtils as futil

DEBUG = True

# Set True to emit structured [PERF] timing lines to the Fusion Text Command
# window from the perf_timer context manager in lib/fusionAddInUtils. Has zero
# runtime cost when False — useful for diagnosing slow Hub operations in the
# Global Parameters commands.
PERF_TRACE = False

ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = "IMA LLC"


design_workspace = "FusionSolidEnvironment"
tools_tab_id = "ToolsTab"
my_tab_name = "Power Tools"

my_panel_id = f"PT_{my_tab_name}"
my_panel_name = "Power Tools"
my_panel_after = ""

# Palettes
assembly_builder_palette_id = f"{COMPANY_NAME.replace(' ', '_')}_{ADDIN_NAME}_assembly_builder_palette"
