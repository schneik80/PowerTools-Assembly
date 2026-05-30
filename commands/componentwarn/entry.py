# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

# PowerTools Assembly - Component Warning.
#
# A passive guard that watches for feature-creation commands (sketches, solids,
# work geometry, patterns, surfaces, ...) and warns the user when the feature
# would land somewhere other than an appropriate component:
#
#   * directly in the root component (i.e. "no component at all"),
#   * in a non-leaf component (optional, off by default), or
#   * while a selection references a different component than the one being
#     edited.
#
# The guard is a toggle in the Power Tools panel. While enabled and while the
# Design (Solid) workspace is active, it listens to ui.commandStarting and pops
# a modal warning before the offending command runs. The warning lets the user
# create the feature anyway, cancel it, or silence the warning for the active
# document.
#
# Behaviour is inspired by Thomas Axelsson's MIT-licensed "NoComponentWarn"
# Fusion 360 add-in; this is an independent reimplementation that follows the
# PowerTools command/handler conventions.

import time

import adsk.core
import adsk.fusion

from ... import config
from ...lib import fusionAddInUtils as futil

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Component Warning"
CMD_ID = "PTAT-componentWarn"
CMD_Description = (
    "Warn before creating a feature outside of a component (directly in the "
    "root component or referencing another component). Toggle on/off."
)
IS_PROMOTED = False

# UI placement (shared Power Tools panel in the Design workspace Utilities tab).
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name
PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Workspace the guard is active in. Outside this workspace the commandStarting
# listener is detached so we never interfere with non-design environments.
SOLID_WORKSPACE_ID = "FusionSolidEnvironment"

# When True, also warn for features created in a component that still has child
# occurrences (a non-leaf component). Off by default, matching the common case
# where intermediate sub-assemblies legitimately hold features.
ONLY_ALLOW_LEAF = False

# A single press of the Sketch button can emit two SketchCreate "starting"
# events back to back. After the user chooses "create anyway" we suppress any
# further warning for this many seconds so they are not prompted twice.
HOLD_OFF_SECONDS = 3.0

# Feature-creation command ids to watch. Each entry is (command_id, is_prefix):
# when is_prefix is True the id is matched as a startswith() prefix so a whole
# family of related commands (e.g. every "Work*" plane/axis/point) is covered.
CREATION_COMMANDS = (
    ("SketchCreate", False),
    ("Primitive", True),
    ("WorkPlane", True),
    ("WorkAxis", True),
    ("WorkPoint", True),
    ("Extrude", False),
    ("Revolve", False),
    ("Sweep", False),
    ("SolidLoft", False),
    ("FusionRibCommand", False),
    ("FusionWebCommand", False),
    ("EmbossCmd", False),
    ("FusionHoleCommand", False),
    ("FusionThreadCommand", False),
    ("PatternRectangular", False),
    ("PatternCircular", False),
    ("PatternOnPath", False),
    ("MirrorCommand", False),
    ("FusionSurfaceThickenCommand", False),
    ("SurfaceSculpt", False),
    ("SurfaceExtrude", False),
    ("SurfaceRevolve", False),
    ("SurfaceSweep", False),
    ("SurfaceLoft", False),
    ("FusionSurfacePatchCommand", False),
    ("FusionSurfaceRuledCommand", False),
    ("FusionSurfaceOffsetCommand", False),
)

# Holds references to the toggle/workspace handlers so they are not released.
local_handlers = []

# Separate reference list + handle for the commandStarting listener so it can be
# attached and detached independently of the persistent handlers above.
_monitor_handlers = []
_starting_handler = None

# Module state.
_enabled = True
# Documents the user silenced via "Stop warning". In-memory only (per session),
# keyed by Document object identity.
_disabled_documents = []
# Timestamp of the last "create anyway" choice, for the hold-off above.
_last_continue_time = 0.0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start():
    # A check-box definition gives the toggle a visible on/off state in the
    # toolbar; it starts checked because the guard defaults to enabled.
    cmd_def = ui.commandDefinitions.addCheckBoxDefinition(
        CMD_ID, CMD_NAME, CMD_Description, _enabled
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)

    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)

    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = IS_PROMOTED

    # Attach/detach the guard as the user moves in and out of the Solid
    # workspace, mirroring the lifetime of the original add-in.
    futil.add_handler(ui.workspaceActivated, workspace_activated)
    futil.add_handler(ui.workspacePreDeactivate, workspace_pre_deactivate)

    # If Fusion has finished starting we can read the active workspace directly;
    # during startup we rely on the workspaceActivated event instead.
    if app.isStartupComplete and ui.activeWorkspace.id == SOLID_WORKSPACE_ID:
        _attach_monitor()


def stop():
    _detach_monitor()

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()

    # The Power Tools panel/tab are shared; only remove them if this command
    # was the last occupant.
    if panel.controls.count == 0:
        panel.deleteMe()
    if toolbar_tab.toolbarPanels.count == 0:
        toolbar_tab.deleteMe()

    global local_handlers
    local_handlers = []


# ---------------------------------------------------------------------------
# Toggle + workspace handlers
# ---------------------------------------------------------------------------


def command_created(args: adsk.core.CommandCreatedEventArgs):
    """Fires each time the user clicks the check-box. Read the new state and
    attach or detach the guard to match."""
    global _enabled
    checkbox = adsk.core.CheckBoxControlDefinition.cast(
        args.command.parentCommandDefinition.controlDefinition
    )
    _enabled = checkbox.isChecked
    futil.log(f"{CMD_NAME}: {'enabled' if _enabled else 'disabled'}")

    in_solid = app.isStartupComplete and ui.activeWorkspace.id == SOLID_WORKSPACE_ID
    if _enabled and in_solid:
        _attach_monitor()
    else:
        _detach_monitor()


def workspace_activated(args: adsk.core.WorkspaceEventArgs):
    if _enabled and args.workspace.id == SOLID_WORKSPACE_ID:
        _attach_monitor()


def workspace_pre_deactivate(args: adsk.core.WorkspaceEventArgs):
    _detach_monitor()


def _attach_monitor():
    """Begin listening to commandStarting. No-op if already listening."""
    global _starting_handler
    if _starting_handler is not None:
        return
    _starting_handler = futil.add_handler(
        ui.commandStarting, command_starting, local_handlers=_monitor_handlers
    )


def _detach_monitor():
    """Stop listening to commandStarting. No-op if not currently listening."""
    global _starting_handler
    if _starting_handler is None:
        return
    try:
        ui.commandStarting.remove(_starting_handler)
    except Exception:
        # If Fusion already tore the event down (e.g. during shutdown) there is
        # nothing left to detach.
        pass
    _starting_handler = None
    _monitor_handlers.clear()


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def command_starting(args: adsk.core.ApplicationCommandEventArgs):
    """Inspect a starting command and, if it is a feature-creation command
    landing in the wrong place, warn the user before it runs."""
    global _last_continue_time

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return

    # Part designs are meant to build features directly in the root component,
    # so there is nothing to warn about. designIntent is an experimental API on
    # some builds, hence the guard.
    try:
        if design.designIntent == adsk.fusion.DesignIntentTypes.PartDesignIntentType:
            return
    except Exception:
        pass

    if app.activeDocument in _disabled_documents:
        return

    # Honour the hold-off after a recent "create anyway" so the doubled
    # SketchCreate event does not prompt twice.
    if time.time() - _last_continue_time < HOLD_OFF_SECONDS:
        return

    if not _is_creation_command(args.commandId):
        return

    edit_component = adsk.fusion.Component.cast(app.activeEditObject)
    if not edit_component:
        return

    warning = _evaluate_placement(design, edit_component)
    if not warning:
        return

    choice = _prompt(warning)
    if choice == _CANCEL:
        args.isCanceled = True
    elif choice == _SILENCE:
        _disabled_documents.append(app.activeDocument)
    else:  # _CONTINUE
        _last_continue_time = time.time()


def _is_creation_command(command_id: str) -> bool:
    for cmd, is_prefix in CREATION_COMMANDS:
        if (is_prefix and command_id.startswith(cmd)) or command_id == cmd:
            return True
    return False


def _evaluate_placement(design: adsk.fusion.Design, edit_component: adsk.fusion.Component):
    """Return a human-readable warning string if the active edit target is an
    inappropriate home for a new feature, otherwise None."""
    if edit_component == design.rootComponent:
        return "You are creating a feature directly in the root component, outside of any component."

    if ONLY_ALLOW_LEAF and edit_component.occurrences.count > 0:
        # A leaf component has no child occurrences.
        return "You are creating a feature in a non-leaf component."

    for selection in ui.activeSelections:
        entity = getattr(selection, "entity", None)
        context = getattr(entity, "assemblyContext", None)
        if context is not None and context.component != app.activeEditObject:
            return "You are creating a feature that references another component."

    return None


# ---------------------------------------------------------------------------
# Warning dialog
# ---------------------------------------------------------------------------

_CONTINUE = "continue"
_CANCEL = "cancel"
_SILENCE = "silence"


def _prompt(warning: str) -> str:
    """Show the modal warning and map the user's choice to one of the three
    actions. Cross-platform via ui.messageBox (Yes/No/Cancel)."""
    message = (
        f"{warning}\n\n"
        "Yes — create it anyway.\n"
        "No — stop warning for this document.\n"
        "Cancel — cancel this command."
    )
    result = ui.messageBox(
        message,
        CMD_NAME,
        adsk.core.MessageBoxButtonTypes.YesNoCancelButtonType,
        adsk.core.MessageBoxIconTypes.WarningIconType,
    )

    if result == adsk.core.DialogResults.DialogCancel:
        return _CANCEL
    if result == adsk.core.DialogResults.DialogNo:
        return _SILENCE
    return _CONTINUE
