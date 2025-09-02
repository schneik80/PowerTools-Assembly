#  Copyright 2022 by Autodesk, Inc.
#  Command registration system for simplified command management

from typing import List, Dict, Type, Any
from .command_base import FusionCommand
from . import general_utils as futil


class CommandRegistry:
    """
    Centralized registry for managing Fusion 360 commands.
    Simplifies command registration and lifecycle management.
    """

    def __init__(self):
        self._commands: Dict[str, FusionCommand] = {}
        self._command_classes: List[Type[FusionCommand]] = []

    def register_command_class(self, command_class: Type[FusionCommand]) -> None:
        """Register a command class to be instantiated and managed"""
        self._command_classes.append(command_class)
        futil.log(f"Registered command class: {command_class.__name__}")

    def register_command_instance(self, command: FusionCommand) -> None:
        """Register a pre-instantiated command"""
        self._commands[command.command_id] = command
        futil.log(f"Registered command instance: {command.command_name}")

    def create_command(
        self, command_class: Type[FusionCommand], *args, **kwargs
    ) -> FusionCommand:
        """Create and register a command instance"""
        command = command_class(*args, **kwargs)
        self.register_command_instance(command)
        return command

    def start_all(self) -> None:
        """Start all registered commands"""
        # Instantiate command classes
        for command_class in self._command_classes:
            try:
                command = command_class()
                self._commands[command.command_id] = command
            except Exception as e:
                futil.handle_error(
                    f"Failed to instantiate {command_class.__name__}: {str(e)}"
                )
                continue

        # Start all command instances
        for command_id, command in self._commands.items():
            try:
                command.start()
                futil.log(f"Started command: {command.command_name}")
            except Exception as e:
                futil.handle_error(f"Failed to start command {command_id}: {str(e)}")

    def stop_all(self) -> None:
        """Stop all registered commands"""
        for command_id, command in self._commands.items():
            try:
                command.stop()
                futil.log(f"Stopped command: {command.command_name}")
            except Exception as e:
                futil.handle_error(f"Failed to stop command {command_id}: {str(e)}")

        # Clear registry
        self._commands.clear()
        self._command_classes.clear()

    def get_command(self, command_id: str) -> FusionCommand:
        """Get a command by ID"""
        return self._commands.get(command_id)

    def list_commands(self) -> List[str]:
        """Get list of registered command IDs"""
        return list(self._commands.keys())

    def get_command_count(self) -> int:
        """Get total number of registered commands"""
        return len(self._commands) + len(self._command_classes)


# Global command registry instance
command_registry = CommandRegistry()
