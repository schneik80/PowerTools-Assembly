#  Optimized configuration system with caching and validation
#  Replaces the simple config.py with a more robust solution

import os
import json
from typing import Dict, Any, Optional
from functools import lru_cache

import adsk.core
from .lib import fusionAddInUtils as futil


class ConfigManager:
    """
    Centralized configuration management with caching and validation.
    Provides better performance and maintainability than global variables.
    """

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._load_default_config()
        self._load_user_config()

    def _load_default_config(self) -> None:
        """Load default configuration values"""
        self._config.update(
            {
                # Debug and logging
                "DEBUG": True,
                "ADDIN_NAME": os.path.basename(os.path.dirname(__file__)),
                "COMPANY_NAME": "IMA LLC",
                # UI Configuration
                "design_workspace": "FusionSolidEnvironment",
                "tools_tab_id": "ToolsTab",
                "my_tab_name": "Power Tools",
                "my_panel_id": "PT_Power Tools",
                "my_panel_name": "Power Tools",
                "my_panel_after": "",
                # Performance settings
                "enable_caching": True,
                "cache_timeout_minutes": 30,
                "max_cache_entries": 100,
                "enable_performance_monitoring": True,
                # UI Behavior
                "auto_save_before_operations": True,
                "show_progress_for_long_operations": True,
                "progress_threshold_seconds": 2.0,
                # Assembly operations
                "skip_non_external_components": False,
                "batch_save_chunk_size": 10,
                "max_component_processing_time": 300,  # 5 minutes
            }
        )

    def _load_user_config(self) -> None:
        """Load user-specific configuration overrides"""
        try:
            config_file = os.path.join(os.path.dirname(__file__), "user_config.json")
            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    user_config = json.load(f)
                    self._config.update(user_config)
                    futil.log(f"Loaded user configuration from {config_file}")
        except Exception as e:
            futil.log(f"Warning: Could not load user config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with optional default"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value"""
        self._config[key] = value

    def update(self, config_dict: Dict[str, Any]) -> None:
        """Update multiple configuration values"""
        self._config.update(config_dict)

    def save_user_config(self) -> None:
        """Save current configuration as user overrides"""
        try:
            config_file = os.path.join(os.path.dirname(__file__), "user_config.json")
            with open(config_file, "w") as f:
                # Only save non-default values
                user_overrides = {
                    k: v
                    for k, v in self._config.items()
                    if k not in self._get_default_keys()
                }
                json.dump(user_overrides, f, indent=2)
                futil.log(f"Saved user configuration to {config_file}")
        except Exception as e:
            futil.log(f"Warning: Could not save user config: {e}")

    def _get_default_keys(self) -> set:
        """Get set of default configuration keys"""
        return {
            "DEBUG",
            "ADDIN_NAME",
            "COMPANY_NAME",
            "design_workspace",
            "tools_tab_id",
            "my_tab_name",
            "my_panel_id",
            "my_panel_name",
            "my_panel_after",
            "enable_caching",
            "cache_timeout_minutes",
            "max_cache_entries",
            "enable_performance_monitoring",
        }

    @property
    def debug_enabled(self) -> bool:
        """Check if debug mode is enabled"""
        return self.get("DEBUG", False)

    @property
    def performance_monitoring_enabled(self) -> bool:
        """Check if performance monitoring is enabled"""
        return self.get("enable_performance_monitoring", True)

    @property
    def caching_enabled(self) -> bool:
        """Check if caching is enabled"""
        return self.get("enable_caching", True)


# Global configuration manager instance
config_manager = ConfigManager()

# Backward compatibility - expose common values as module-level variables
DEBUG = config_manager.debug_enabled
ADDIN_NAME = config_manager.get("ADDIN_NAME")
COMPANY_NAME = config_manager.get("COMPANY_NAME")

design_workspace = config_manager.get("design_workspace")
tools_tab_id = config_manager.get("tools_tab_id")
my_tab_name = config_manager.get("my_tab_name")
my_panel_id = config_manager.get("my_panel_id")
my_panel_name = config_manager.get("my_panel_name")
my_panel_after = config_manager.get("my_panel_after")


# Configuration validation helpers
@lru_cache(maxsize=32)
def validate_workspace(workspace_id: str) -> bool:
    """Validate that a workspace exists"""
    try:
        app = adsk.core.Application.get()
        workspace = app.userInterface.workspaces.itemById(workspace_id)
        return workspace is not None
    except:
        return False


@lru_cache(maxsize=32)
def get_available_workspaces() -> list:
    """Get list of available workspace IDs"""
    try:
        app = adsk.core.Application.get()
        return [ws.id for ws in app.userInterface.workspaces]
    except:
        return []


def validate_config() -> Dict[str, Any]:
    """Validate current configuration and return status report"""
    report = {"valid": True, "warnings": [], "errors": []}

    # Validate workspace
    workspace_id = config_manager.get("design_workspace")
    if not validate_workspace(workspace_id):
        report["errors"].append(f"Invalid workspace ID: {workspace_id}")
        report["valid"] = False

    # Validate numeric settings
    numeric_settings = [
        ("cache_timeout_minutes", 1, 1440),  # 1 min to 24 hours
        ("max_cache_entries", 10, 10000),
        ("progress_threshold_seconds", 0.1, 60.0),
        ("batch_save_chunk_size", 1, 100),
        ("max_component_processing_time", 30, 3600),  # 30 sec to 1 hour
    ]

    for setting, min_val, max_val in numeric_settings:
        value = config_manager.get(setting)
        if not isinstance(value, (int, float)) or not (min_val <= value <= max_val):
            report["warnings"].append(
                f"Invalid {setting}: {value} (should be {min_val}-{max_val})"
            )

    return report


# Initialize and validate configuration on import
_config_report = validate_config()
if not _config_report["valid"]:
    futil.log("Configuration validation failed:")
    for error in _config_report["errors"]:
        futil.log(f"ERROR: {error}")

if _config_report["warnings"]:
    for warning in _config_report["warnings"]:
        futil.log(f"WARNING: {warning}")
