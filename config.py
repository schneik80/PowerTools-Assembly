import adsk.core
import os
import os.path
import json
from .lib import fusionAddInUtils as futil

DEBUG = True
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = "IMA LLC"


design_workspace = "FusionSolidEnvironment"
tools_tab_id = "ToolsTab"
my_tab_name = "Power Tools"

my_panel_id = f"{ADDIN_NAME}_panel_2"
my_panel_name = "Tools"
my_panel_after = ""
