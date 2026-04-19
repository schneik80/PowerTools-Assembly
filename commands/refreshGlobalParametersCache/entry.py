# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core
import os
from ...lib import fusionAddInUtils as futil
from ...lib.fusionAddInUtils import cache_utils as cache
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

# Command identity
CMD_ID = "PTAT-refreshGlobalParametersCache"
CMD_NAME = "Refresh Global Parameters Cache"
CMD_Description = "Scan the active project for global parameter sets and update the cache."

# QAT flyout (shared across PowerTools add-ins — create only if absent).
PT_SETTINGS_ID = "PTSettings"
PT_SETTINGS_NAME = "PowerTools Settings"

# UI placement (reuse config from other commands)
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
PANEL_ID = config.my_panel_id
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")
IS_PROMOTED = False

def start():
    existing_def = ui.commandDefinitions.itemById(CMD_ID)
    if existing_def:
        existing_def.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    # Add to PowerTools Settings submenu in File menu (QAT)
    qat = ui.toolbars.itemById("QAT")
    file_dropdown = adsk.core.DropDownControl.cast(
        qat.controls.itemById("FileSubMenuCommand")
    )

    pt_settings_control = file_dropdown.controls.itemById(PT_SETTINGS_ID)
    if not pt_settings_control:
        pt_settings = file_dropdown.controls.addDropDown(
            PT_SETTINGS_NAME, "", PT_SETTINGS_ID
        )
    else:
        pt_settings = adsk.core.DropDownControl.cast(pt_settings_control)

    pt_settings.controls.addCommand(cmd_def)

def stop():

    qat = ui.toolbars.itemById("QAT")
    file_dropdown = adsk.core.DropDownControl.cast(
        qat.controls.itemById("FileSubMenuCommand")
    )
    pt_settings = adsk.core.DropDownControl.cast(
        file_dropdown.controls.itemById(PT_SETTINGS_ID)
    )

    if pt_settings:
        command_control = pt_settings.controls.itemById(CMD_ID)
        if command_control:
            command_control.deleteMe()

        if pt_settings.controls.count == 0:
            pt_settings.deleteMe()

    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()

def command_created(args):
    futil.log(f"{CMD_NAME} Command Created Event")
    refresh_cache_for_active_project()


def refresh_cache_for_active_project():
    """Scan the active project and write the canonical gp_folder and gp_docs caches.

    Always does a fresh Hub scan (ignores any existing cache) so the result
    reflects the current state of the project.  Writes the same files that
    Global Parameters and Link Global Parameters read at startup.
    """
    project = cache.get_active_project(CMD_NAME)
    if not project:
        ui.messageBox("No active Fusion project found.")
        return

    # Bypass the cache-first lookup — this command exists to fix a stale cache.
    root = project.rootFolder
    folder = None
    try:
        for i in range(root.dataFolders.count):
            f = root.dataFolders.item(i)
            if f.name == cache.GLOBAL_PARAMS_FOLDER_NAME:
                folder = f
                break
    except Exception:
        futil.handle_error(CMD_NAME)
        return

    if not folder:
        ui.messageBox(
            f"No '{cache.GLOBAL_PARAMS_FOLDER_NAME}' folder found in this project."
        )
        return

    # Write both cache files via cache_utils so the format stays consistent.
    cache.write_global_params_folder_cache(project, folder, CMD_NAME)

    doc_map = {}
    for i in range(folder.dataFiles.count):
        df = folder.dataFiles.item(i)
        doc_map[df.name] = df
    cache.write_param_docs_cache(project, doc_map, CMD_NAME)

    n = len(doc_map)
    futil.log(f"{CMD_NAME}: cache refreshed — {n} parameter set(s) found")
    ui.messageBox(
        f"Global Parameters cache refreshed for project '{project.name}'.\n"
        f"{n} parameter set(s) found."
    )
