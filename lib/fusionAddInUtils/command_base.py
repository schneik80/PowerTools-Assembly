#  Copyright 2022 by Autodesk, Inc.
#  Performance-optimized base classes for Fusion 360 commands

import os
import traceback
from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any, List
from enum import Enum

import adsk.core
import adsk.fusion

from . import general_utils as futil


class UIPlacement(Enum):
    """Enumeration of UI placement strategies"""

    POWER_TOOLS_TAB = "power_tools"
    QUICK_ACCESS_TOOLBAR = "qat"
    FILE_MENU = "file_menu"
    ASSEMBLY_TAB = "assembly_tab"


class FusionCommand(ABC):
    """
    High-performance base class for Fusion 360 commands.
    Eliminates code duplication and provides optimized UI management.
    """

    # Class-level cache for UI elements to avoid repeated lookups
    _ui_cache: Dict[str, Any] = {}

    def __init__(
        self,
        command_name: str,
        command_id: str,
        command_description: str,
        ui_placement: UIPlacement = UIPlacement.POWER_TOOLS_TAB,
        is_promoted: bool = False,
        icon_folder: Optional[str] = None,
    ):

        self.command_name = command_name
        self.command_id = command_id
        self.command_description = command_description
        self.ui_placement = ui_placement
        self.is_promoted = is_promoted

        # Performance: Cache frequently accessed objects
        self._app = adsk.core.Application.get()
        self._ui = self._app.userInterface

        # Auto-detect icon folder if not provided
        if icon_folder is None:
            caller_file = os.path.dirname(os.path.abspath(__file__))
            self.icon_folder = os.path.join(
                os.path.dirname(caller_file), "resources", ""
            )
        else:
            self.icon_folder = icon_folder

        # Event handler references (prevents garbage collection)
        self.local_handlers: List[Any] = []

        # Lazy-loaded properties
        self._design: Optional[adsk.fusion.Design] = None
        self._root_component: Optional[adsk.fusion.Component] = None

    @property
    def app(self) -> adsk.core.Application:
        """Cached application reference"""
        return self._app

    @property
    def ui(self) -> adsk.core.UserInterface:
        """Cached UI reference"""
        return self._ui

    @property
    def design(self) -> Optional[adsk.fusion.Design]:
        """Lazy-loaded design with caching"""
        if self._design is None:
            product = self.app.activeProduct
            self._design = adsk.fusion.Design.cast(product) if product else None
        return self._design

    @property
    def root_component(self) -> Optional[adsk.fusion.Component]:
        """Lazy-loaded root component with caching"""
        if self._root_component is None and self.design:
            self._root_component = self.design.rootComponent
        return self._root_component

    def invalidate_cache(self) -> None:
        """Clear cached properties when document changes"""
        self._design = None
        self._root_component = None

    def start(self) -> None:
        """Create command definition and UI control"""
        try:
            # Create command definition
            cmd_def = self._create_command_definition()

            # Add command created handler
            futil.add_handler(cmd_def.commandCreated, self._command_created_handler)

            # Create UI control based on placement strategy
            control = self._create_ui_control(cmd_def)
            control.isPromoted = self.is_promoted

            futil.log(f"{self.command_name} started successfully")

        except Exception as e:
            futil.handle_error(f"Failed to start {self.command_name}: {str(e)}")

    def stop(self) -> None:
        """Clean up command definition and UI control"""
        try:
            # Get UI elements using cached lookups
            control, definition = self._get_ui_elements_for_cleanup()

            # Clean up control
            if control:
                control.deleteMe()

            # Clean up definition
            if definition:
                definition.deleteMe()

            # Clean up empty containers
            self._cleanup_empty_containers()

            futil.log(f"{self.command_name} stopped successfully")

        except Exception as e:
            futil.handle_error(f"Failed to stop {self.command_name}: {str(e)}")

    def _create_command_definition(self) -> adsk.core.CommandDefinition:
        """Create command definition with proper icon handling"""
        return self.ui.commandDefinitions.addButtonDefinition(
            self.command_id,
            self.command_name,
            self.command_description,
            self.icon_folder,
        )

    def _create_ui_control(
        self, cmd_def: adsk.core.CommandDefinition
    ) -> adsk.core.Control:
        """Create UI control using strategy pattern"""
        placement_strategies = {
            UIPlacement.POWER_TOOLS_TAB: self._create_power_tools_control,
            UIPlacement.QUICK_ACCESS_TOOLBAR: self._create_qat_control,
            UIPlacement.FILE_MENU: self._create_file_menu_control,
            UIPlacement.ASSEMBLY_TAB: self._create_assembly_control,
        }

        strategy = placement_strategies.get(self.ui_placement)
        if not strategy:
            raise ValueError(f"Unsupported UI placement: {self.ui_placement}")

        return strategy(cmd_def)

    def _create_power_tools_control(
        self, cmd_def: adsk.core.CommandDefinition
    ) -> adsk.core.Control:
        """Create control in Power Tools tab (performance optimized)"""
        # Use cached workspace lookup
        workspace_key = "FusionSolidEnvironment"
        workspace = self._get_cached_ui_element(
            "workspace",
            workspace_key,
            lambda: self.ui.workspaces.itemById(workspace_key),
        )

        # Create/get toolbar tab
        tab = self._get_or_create_toolbar_tab(workspace, "ToolsTab", "Power Tools")

        # Create/get panel
        panel = self._get_or_create_panel(tab, "PT_Power Tools", "Power Tools", "")

        # Create control
        return panel.controls.addCommand(cmd_def)

    def _create_qat_control(
        self, cmd_def: adsk.core.CommandDefinition
    ) -> adsk.core.Control:
        """Create control in Quick Access Toolbar"""
        qat = self._get_cached_ui_element(
            "qat", "QAT", lambda: self.ui.toolbars.itemById("QAT")
        )
        return qat.controls.addCommand(cmd_def, "save", True)

    def _create_file_menu_control(
        self, cmd_def: adsk.core.CommandDefinition
    ) -> adsk.core.Control:
        """Create control in File menu"""
        qat = self._get_cached_ui_element(
            "qat", "QAT", lambda: self.ui.toolbars.itemById("QAT")
        )
        file_dropdown = qat.controls.itemById("FileSubMenuCommand")
        return file_dropdown.controls.addCommand(cmd_def, "ExportCommand", False)

    def _create_assembly_control(
        self, cmd_def: adsk.core.CommandDefinition
    ) -> adsk.core.Control:
        """Create control in Assembly tab or fallback to Solid tab"""
        workspace = self._get_cached_ui_element(
            "workspace",
            "FusionSolidEnvironment",
            lambda: self.ui.workspaces.itemById("FusionSolidEnvironment"),
        )

        # Try Assembly tab first
        tab = workspace.toolbarTabs.itemById("AssemblyTab")
        if tab:
            panel = self._get_or_create_panel(
                tab, "AssemblyAssemblePanel", "Assemble", ""
            )
        else:
            # Fallback to Solid tab
            tab = self._get_or_create_toolbar_tab(workspace, "SolidTab", "SOLID")
            panel = self._get_or_create_panel(tab, "InsertPanel", "Insert", "")

        return panel.controls.addCommand(cmd_def, "PT-assemblystats", True)

    def _get_cached_ui_element(
        self, cache_key: str, element_id: str, factory: Callable
    ) -> Any:
        """Get UI element with caching for performance"""
        full_key = f"{cache_key}_{element_id}"
        if full_key not in self._ui_cache:
            self._ui_cache[full_key] = factory()
        return self._ui_cache[full_key]

    def _get_or_create_toolbar_tab(self, workspace, tab_id: str, tab_name: str):
        """Get or create toolbar tab with caching"""
        tab = workspace.toolbarTabs.itemById(tab_id)
        if tab is None:
            tab = workspace.toolbarTabs.add(tab_id, tab_name)
        return tab

    def _get_or_create_panel(
        self, tab, panel_id: str, panel_name: str, panel_after: str
    ):
        """Get or create panel with caching"""
        panel = tab.toolbarPanels.itemById(panel_id)
        if panel is None:
            panel = tab.toolbarPanels.add(panel_id, panel_name, panel_after, False)
        return panel

    def _command_created_handler(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        """Handle command creation with error handling"""
        try:
            futil.log(f"{self.command_name} Command Created Event")

            # Validate prerequisites
            if not self._validate_prerequisites():
                return

            # Connect events
            futil.add_handler(
                args.command.execute,
                self._command_execute_handler,
                local_handlers=self.local_handlers,
            )
            futil.add_handler(
                args.command.destroy,
                self._command_destroy_handler,
                local_handlers=self.local_handlers,
            )

            # Call custom command creation logic
            self.on_command_created(args)

        except Exception as e:
            futil.handle_error(f"{self.command_name} command creation failed: {str(e)}")

    def _command_execute_handler(self, args: adsk.core.CommandEventArgs) -> None:
        """Handle command execution with error handling"""
        try:
            futil.log(f"{self.command_name} Command Execute Event")

            # Invalidate cache in case document changed
            self.invalidate_cache()

            # Call custom execution logic
            self.on_command_execute(args)

        except Exception as e:
            futil.handle_error(
                f"{self.command_name} execution failed: {str(e)}", show_message_box=True
            )

    def _command_destroy_handler(self, args: adsk.core.CommandEventArgs) -> None:
        """Handle command destruction with cleanup"""
        try:
            # Clear local handlers
            self.local_handlers.clear()

            # Call custom cleanup logic
            self.on_command_destroy(args)

            futil.log(f"{self.command_name} Command Destroy Event")

        except Exception as e:
            futil.handle_error(f"{self.command_name} cleanup failed: {str(e)}")

    def _validate_prerequisites(self) -> bool:
        """Validate common prerequisites"""
        # Check if design is active
        if not self.design:
            self.ui.messageBox("A Fusion 3D Design must be active", self.command_name)
            return False

        # Check if document is saved
        if not futil.isSaved():
            return False

        return True

    def _get_ui_elements_for_cleanup(self) -> tuple:
        """Get UI elements for cleanup based on placement strategy"""
        cleanup_strategies = {
            UIPlacement.POWER_TOOLS_TAB: self._get_power_tools_elements,
            UIPlacement.QUICK_ACCESS_TOOLBAR: self._get_qat_elements,
            UIPlacement.FILE_MENU: self._get_file_menu_elements,
            UIPlacement.ASSEMBLY_TAB: self._get_assembly_elements,
        }

        strategy = cleanup_strategies.get(self.ui_placement)
        if strategy:
            return strategy()
        return None, None

    def _get_power_tools_elements(self) -> tuple:
        """Get Power Tools UI elements for cleanup"""
        workspace = self.ui.workspaces.itemById("FusionSolidEnvironment")
        panel = (
            workspace.toolbarPanels.itemById("PT_Power Tools") if workspace else None
        )
        control = panel.controls.itemById(self.command_id) if panel else None
        definition = self.ui.commandDefinitions.itemById(self.command_id)
        return control, definition

    def _get_qat_elements(self) -> tuple:
        """Get QAT UI elements for cleanup"""
        qat = self.ui.toolbars.itemById("QAT")
        control = qat.controls.itemById(self.command_id) if qat else None
        definition = self.ui.commandDefinitions.itemById(self.command_id)
        return control, definition

    def _get_file_menu_elements(self) -> tuple:
        """Get File menu UI elements for cleanup"""
        qat = self.ui.toolbars.itemById("QAT")
        file_dropdown = qat.controls.itemById("FileSubMenuCommand") if qat else None
        control = (
            file_dropdown.controls.itemById(self.command_id) if file_dropdown else None
        )
        definition = self.ui.commandDefinitions.itemById(self.command_id)
        return control, definition

    def _get_assembly_elements(self) -> tuple:
        """Get Assembly tab UI elements for cleanup"""
        workspace = self.ui.workspaces.itemById("FusionSolidEnvironment")

        # Try Assembly tab first
        tab = workspace.toolbarTabs.itemById("AssemblyTab") if workspace else None
        if tab:
            panel = tab.toolbarPanels.itemById("AssemblyAssemblePanel")
        else:
            # Fallback to Solid tab
            tab = workspace.toolbarTabs.itemById("SolidTab") if workspace else None
            panel = tab.toolbarPanels.itemById("InsertPanel") if tab else None

        control = panel.controls.itemById(self.command_id) if panel else None
        definition = self.ui.commandDefinitions.itemById(self.command_id)
        return control, definition

    def _cleanup_empty_containers(self) -> None:
        """Clean up empty panels and tabs"""
        try:
            if self.ui_placement == UIPlacement.POWER_TOOLS_TAB:
                workspace = self.ui.workspaces.itemById("FusionSolidEnvironment")
                if workspace:
                    panel = workspace.toolbarPanels.itemById("PT_Power Tools")
                    tab = workspace.toolbarTabs.itemById("ToolsTab")

                    if panel and panel.controls.count == 0:
                        panel.deleteMe()

                    if tab and tab.toolbarPanels.count == 0:
                        tab.deleteMe()

        except Exception as e:
            # Non-critical cleanup failure
            futil.log(f"Container cleanup warning: {str(e)}")

    # Abstract methods for subclasses to implement
    @abstractmethod
    def on_command_execute(self, args: adsk.core.CommandEventArgs) -> None:
        """Override this method to implement command-specific execution logic"""
        pass

    def on_command_created(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        """Override this method for custom command creation logic"""
        pass

    def on_command_destroy(self, args: adsk.core.CommandEventArgs) -> None:
        """Override this method for custom cleanup logic"""
        pass


class SimpleCommand(FusionCommand):
    """
    Command that executes immediately when clicked (no dialog)
    """

    def __init__(
        self,
        command_name: str,
        command_id: str,
        command_description: str,
        execute_function: Callable[[adsk.core.CommandEventArgs], None],
        ui_placement: UIPlacement = UIPlacement.POWER_TOOLS_TAB,
        **kwargs,
    ):
        super().__init__(
            command_name, command_id, command_description, ui_placement, **kwargs
        )
        self.execute_function = execute_function

    def on_command_created(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        """Execute immediately without showing dialog"""
        try:
            self.execute_function(args)
        except Exception as e:
            futil.handle_error(
                f"{self.command_name} execution failed: {str(e)}", show_message_box=True
            )

    def on_command_execute(self, args: adsk.core.CommandEventArgs) -> None:
        """Not used for simple commands"""
        pass


class DialogCommand(FusionCommand):
    """
    Command that shows a dialog for user input
    """

    def on_command_created(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        """Set up command dialog"""
        # Dialog setup will be implemented by subclasses
        pass
