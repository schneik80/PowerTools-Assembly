# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
#
# Part of fusionAddInUtils — kept byte-for-byte in sync across all PowerTools add-ins.
#
# Helpers for the three shared UI locations used by PowerTools commands:
#   1. The "Power Tools" toolbar panel (ToolsTab in FusionSolidEnvironment)
#   2. The PTSettings flyout inside the QAT File dropdown
#   3. The QATRight share flyout
#
# Every helper guards against None at every itemById() call so that a missing
# QAT control or workspace does not cascade into an AttributeError that prevents
# subsequent commands from starting.

import adsk.core


def _ui():
    return adsk.core.Application.get().userInterface


# ── Toolbar panel ─────────────────────────────────────────────────────────────

def get_or_create_panel(workspace_id, tab_id, tab_name, panel_id, panel_name, panel_after=""):
    """Find or create a toolbar panel on the given workspace tab.

    Creates the tab if it does not exist.  Returns the panel, or None if the
    workspace itself cannot be found (e.g. wrong workspace ID).
    """
    workspace = _ui().workspaces.itemById(workspace_id)
    if workspace is None:
        return None
    tab = workspace.toolbarTabs.itemById(tab_id)
    if tab is None:
        tab = workspace.toolbarTabs.add(tab_id, tab_name)
    panel = tab.toolbarPanels.itemById(panel_id)
    if panel is None:
        panel = tab.toolbarPanels.add(panel_id, panel_name, panel_after, False)
    return panel


def remove_from_panel(workspace_id, panel_id, tab_id, control_id):
    """Remove *control_id* from the panel.

    Deletes the panel when it becomes empty, then deletes the tab when it has
    no remaining panels.  Safe to call even if the panel or tab is already gone.
    """
    workspace = _ui().workspaces.itemById(workspace_id)
    if workspace is None:
        return
    panel = workspace.toolbarPanels.itemById(panel_id)
    if panel is not None:
        ctrl = panel.controls.itemById(control_id)
        if ctrl:
            ctrl.deleteMe()
        if panel.controls.count == 0:
            panel.deleteMe()
    tab = workspace.toolbarTabs.itemById(tab_id)
    if tab is not None and tab.toolbarPanels.count == 0:
        tab.deleteMe()


# ── QAT File dropdown ─────────────────────────────────────────────────────────

def get_qat_file_dropdown():
    """Return the QAT FileSubMenuCommand DropDownControl, or None.

    Returns None when the QAT toolbar or the File dropdown control is absent
    (e.g. a future Fusion version that renames the control).
    """
    qat = _ui().toolbars.itemById("QAT")
    if qat is None:
        return None
    return adsk.core.DropDownControl.cast(qat.controls.itemById("FileSubMenuCommand"))


def get_or_create_qat_file_flyout(flyout_id, flyout_name):
    """Find or create a named flyout submenu inside the QAT File dropdown.

    Returns None when the QAT or File dropdown is not available, so callers
    can guard with ``if flyout:`` before adding commands.
    """
    file_dd = get_qat_file_dropdown()
    if file_dd is None:
        return None
    existing = file_dd.controls.itemById(flyout_id)
    if existing:
        return adsk.core.DropDownControl.cast(existing)
    return file_dd.controls.addDropDown(flyout_name, "", flyout_id)


def remove_from_qat_file_flyout(control_id, flyout_id):
    """Remove *control_id* from the named QAT File flyout.

    Deletes the flyout itself when the last child is removed, so the shared
    submenu disappears automatically when all commands that registered to it
    have been stopped.
    """
    file_dd = get_qat_file_dropdown()
    if file_dd is None:
        return
    flyout = adsk.core.DropDownControl.cast(file_dd.controls.itemById(flyout_id))
    if flyout is None:
        return
    ctrl = flyout.controls.itemById(control_id)
    if ctrl:
        ctrl.deleteMe()
    if flyout.controls.count == 0:
        flyout.deleteMe()


def remove_from_qat_file_dropdown(control_id):
    """Remove a direct child control from the QAT File dropdown."""
    file_dd = get_qat_file_dropdown()
    if file_dd is None:
        return
    ctrl = file_dd.controls.itemById(control_id)
    if ctrl:
        ctrl.deleteMe()


# ── QATRight flyout ───────────────────────────────────────────────────────────

def get_or_create_qat_right_flyout(flyout_id, flyout_name, icon_folder="", after_id="", is_before=True):
    """Find or create a flyout dropdown on the QATRight toolbar.

    Returns None when QATRight is not available.
    """
    qat_right = _ui().toolbars.itemById("QATRight")
    if qat_right is None:
        return None
    existing = qat_right.controls.itemById(flyout_id)
    if existing:
        return adsk.core.DropDownControl.cast(existing)
    return qat_right.controls.addDropDown(flyout_name, icon_folder, flyout_id, after_id, is_before)


def remove_from_qat_right_flyout(control_id, flyout_id):
    """Remove *control_id* from a QATRight flyout.

    Deletes the flyout itself when the last child is removed.
    """
    qat_right = _ui().toolbars.itemById("QATRight")
    if qat_right is None:
        return
    flyout = adsk.core.DropDownControl.cast(qat_right.controls.itemById(flyout_id))
    if flyout is None:
        return
    ctrl = flyout.controls.itemById(control_id)
    if ctrl:
        ctrl.deleteMe()
    if flyout.controls.count == 0:
        flyout.deleteMe()
