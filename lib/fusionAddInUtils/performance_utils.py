#  Copyright 2022 by Autodesk, Inc.
#  Performance-optimized utility functions for Fusion 360 commands

import re
import time
from typing import Dict, List, Any, Optional, Generator, Tuple
from functools import lru_cache, wraps
from contextlib import contextmanager

import adsk.core
import adsk.fusion

from . import general_utils as futil


def timed_operation(func):
    """Decorator to time operations for performance monitoring"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        futil.log(f"{func.__name__} completed in {end_time - start_time:.3f} seconds")
        return result

    return wrapper


@contextmanager
def progress_bar(title: str, show_busy: bool = True):
    """Context manager for progress bar with automatic cleanup"""
    app = adsk.core.Application.get()
    ui = app.userInterface
    progress_bar = ui.progressBar

    try:
        if show_busy:
            progress_bar.showBusy(title, True)
        else:
            progress_bar.show(title, "Processing", 0, 100, 0)
        adsk.doEvents()
        yield progress_bar
    finally:
        progress_bar.hide()


class FusionDocumentAnalyzer:
    """High-performance document analysis with caching"""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._app = adsk.core.Application.get()
        self._last_doc_id: Optional[str] = None

    def _get_cache_key(self, operation: str) -> str:
        """Generate cache key based on document and operation"""
        doc = self._app.activeDocument
        doc_id = doc.dataFile.id if doc and doc.dataFile else "no_doc"

        # Clear cache if document changed
        if self._last_doc_id != doc_id:
            self._cache.clear()
            self._last_doc_id = doc_id

        return f"{doc_id}_{operation}"

    @timed_operation
    def get_out_of_date_references(self) -> int:
        """Get count of out-of-date references with caching"""
        cache_key = self._get_cache_key("out_of_date_refs")

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            count = sum(
                1
                for ref in self._app.activeDocument.documentReferences
                if ref.isOutOfDate
            )
            self._cache[cache_key] = count
            return count
        except Exception as e:
            futil.log(f"Error counting out-of-date references: {e}")
            return 0

    @timed_operation
    def get_component_statistics(self) -> Dict[str, Any]:
        """Get comprehensive component statistics with caching"""
        cache_key = self._get_cache_key("component_stats")

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            design = adsk.fusion.Design.cast(self._app.activeProduct)
            if not design:
                return {}

            root_comp = design.rootComponent

            stats = {
                "total_unique_components": design.allComponents.count
                - 1,  # Exclude root
                "total_component_instances": root_comp.allOccurrences.count,
                "assembly_constraints": root_comp.assemblyConstraints.count,
                "tangent_relationships": root_comp.tangentRelationships.count,
                "rigid_groups": root_comp.rigidGroups.count,
                "out_of_date_references": self.get_out_of_date_references(),
            }

            self._cache[cache_key] = stats
            return stats

        except Exception as e:
            futil.log(f"Error getting component statistics: {e}")
            return {}

    @timed_operation
    def get_hierarchy_analysis(self) -> List[str]:
        """Get assembly hierarchy analysis with optimized parsing"""
        cache_key = self._get_cache_key("hierarchy")

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            # Execute text command once and cache result
            stats = self._app.executeTextCommand("Component.AnalyseHierarchy")

            # Optimized regex pattern compilation
            pattern = re.compile(r"^[a-zA-Z]\.+\D|\d\.+\D")

            # Process lines in single pass
            processed_lines = [pattern.sub("", line) for line in stats.splitlines()]

            self._cache[cache_key] = processed_lines
            return processed_lines

        except Exception as e:
            futil.log(f"Error getting hierarchy analysis: {e}")
            return []

    @timed_operation
    def get_timeline_contexts(self) -> int:
        """Get timeline context count with caching"""
        cache_key = self._get_cache_key("timeline_contexts")

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            timeline_output = self._app.executeTextCommand("timeline.print")
            # Count lines containing "Context" in single pass
            count = sum(
                1 for line in timeline_output.strip().split("\n") if "Context" in line
            )

            self._cache[cache_key] = count
            return count

        except Exception as e:
            futil.log("Error retrieving timeline contexts")
            return 0


class DocumentReferenceManager:
    """Optimized document reference analysis"""

    @staticmethod
    @timed_operation
    def analyze_document_references() -> Dict[str, List[Dict[str, str]]]:
        """Analyze document references with optimized single-pass processing"""
        app = adsk.core.Application.get()
        doc = app.activeDocument

        if not doc:
            return {}

        parent_refs = doc.designDataFile.parentReferences
        child_refs = doc.designDataFile.childReferences

        # Initialize result structure
        result = {
            "parents": [],
            "children": [],
            "drawings": [],
            "related": [],
            "fasteners": [],
        }

        # Process parent references
        if parent_refs:
            for file in parent_refs:
                file_data = DocumentReferenceManager._create_file_data(file)

                if " ‹+› " in file.name:
                    result["related"].append(file_data)
                elif file.fileExtension == "f2d":
                    result["drawings"].append(file_data)
                else:
                    result["parents"].append(file_data)

        # Process child references
        if child_refs:
            for file in child_refs:
                file_data = DocumentReferenceManager._create_file_data(file)

                try:
                    if file.parentProject and file.parentProject.name == "Fasteners":
                        result["fasteners"].append(file_data)
                    else:
                        # Check for configuration
                        if hasattr(file, "isConfiguration") and file.isConfiguration:
                            file_data["name"] += " (configuration)"
                        result["children"].append(file_data)
                except:
                    # Handle case where parentProject is not accessible
                    try:
                        if hasattr(file, "isConfiguration") and file.isConfiguration:
                            file_data["name"] += " (configuration)"
                    except:
                        pass
                    result["children"].append(file_data)

        return result

    @staticmethod
    def _create_file_data(file) -> Dict[str, str]:
        """Create optimized file data structure"""
        url = None
        try:
            url = file.fusionWebURL
        except:
            pass

        return {"name": file.name, "id": file.id, "url": url}

    @staticmethod
    def format_references_html(
        references: Dict[str, List[Dict[str, str]]],
    ) -> Tuple[str, bool]:
        """Format references as HTML with link error tracking"""
        html_parts = []
        link_error = False

        section_configs = [
            ("parents", "Parents"),
            ("children", "Children"),
            ("drawings", "Drawings"),
            ("related", "Related Data"),
            ("fasteners", "Fasteners"),
        ]

        for key, title in section_configs:
            items = references.get(key, [])
            if items:
                html_parts.append(f"<h3>{title} ({len(items)}):</h3>")

                for item in items:
                    if item["url"]:
                        html_parts.append(
                            f'<a href="{item["url"]}">{item["name"]}</a><br>'
                        )
                    else:
                        html_parts.append(f'{item["name"]}<br>')
                        link_error = True

        html = "".join(html_parts)

        if link_error:
            html += "<br><b>Note:</b> Some links may not be accessible due to permissions or other issues.<br>"

        return html, link_error


class AssemblyTraverser:
    """High-performance assembly traversal utilities"""

    @staticmethod
    @timed_operation
    def traverse_bottom_up(root_component: adsk.fusion.Component) -> List[str]:
        """
        Traverse assembly in bottom-up order using optimized DAG algorithm.
        Returns components sorted from leaves to root for efficient processing.
        """
        # Build assembly dictionary in single traversal
        assembly_dict = {}
        AssemblyTraverser._build_assembly_tree(root_component, assembly_dict)

        # Sort using optimized DAG traversal
        return AssemblyTraverser._sort_bottom_up(assembly_dict)

    @staticmethod
    def _build_assembly_tree(
        component: adsk.fusion.Component, parent_dict: Dict[str, Any]
    ) -> None:
        """Build assembly tree structure with single traversal"""
        for occurrence in component.occurrences:
            child_component = occurrence.component
            child_name = child_component.name

            if child_name not in parent_dict:
                parent_dict[child_name] = {"component": child_component, "children": {}}

            # Recursively process children
            AssemblyTraverser._build_assembly_tree(
                child_component, parent_dict[child_name]["children"]
            )

    @staticmethod
    def _sort_bottom_up(assembly_dict: Dict[str, Any]) -> List[str]:
        """Sort assembly dictionary in bottom-up order using DFS"""
        sorted_components = []

        def dfs_traverse(node: Dict[str, Any]) -> None:
            # Process all children first (bottom-up)
            for child_data in node["children"].values():
                dfs_traverse(child_data)

            # Add current component after children
            sorted_components.append(node["component"].name)

        # Process all root-level components
        for node in assembly_dict.values():
            dfs_traverse(node)

        return sorted_components

    @staticmethod
    def is_external_component(component: adsk.fusion.Component) -> bool:
        """Check if component is external (optimized)"""
        try:
            app = adsk.core.Application.get()
            design = app.activeProduct
            root = design.rootComponent

            # Get all occurrences for this component
            occurrences = root.occurrencesByComponent(component)

            # Check if any occurrence is a referenced component
            return any(occ.isReferencedComponent for occ in occurrences)

        except Exception as e:
            futil.log(f"Error checking external component: {e}")
            return False


class BulkOperationManager:
    """Manager for bulk operations with progress tracking"""

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface
        self.processed_docs = set()

    @contextmanager
    def bulk_document_processing(self, total_items: int):
        """Context manager for bulk document operations"""
        with progress_bar(f"Processing {total_items} items", False) as pbar:
            try:
                yield pbar
            finally:
                # Ensure we're back to the original document
                pass

    def save_component_document(
        self, component: adsk.fusion.Component, app_version: str
    ) -> bool:
        """Save component document with duplicate prevention"""
        try:
            doc_id = component.parentDesign.parentDocument.designDataFile.id

            # Skip if already processed
            if doc_id in self.processed_docs:
                return True

            self.processed_docs.add(doc_id)

            # Open document
            document = self.app.data.findFileById(doc_id)
            self.app.documents.open(document, False)

            # Ensure design workspace is active
            workspace = self.ui.workspaces.itemById("FusionSolidEnvironment")
            if workspace and not workspace.isActive:
                workspace.activate()

            # Add temporary attribute for version tracking
            design = adsk.fusion.Design.cast(self.app.activeProduct)
            design.attributes.add("FusionRA", "FusionRA", component.name)
            attr = design.attributes.itemByName("FusionRA", "FusionRA")
            attr.deleteMe()

            # Save with descriptive comment
            self.app.activeDocument.save(
                f"Auto save in Fusion: {app_version}, by {self.operation_name}"
            )

            # Close document
            self.app.activeDocument.close(True)
            futil.log(f"Component {component.name} saved successfully")

            return True

        except Exception as e:
            futil.log(f"Error saving component {component.name}: {e}")
            return False

    def execute_fusion_commands(self, command_ids: List[str]) -> bool:
        """Execute multiple Fusion commands with error handling"""
        try:
            cmd_defs = self.ui.commandDefinitions

            for cmd_id in command_ids:
                cmd = cmd_defs.itemById(cmd_id)
                if cmd:
                    cmd.execute()
                else:
                    futil.log(f"Command {cmd_id} not found")
                    return False

            return True

        except Exception as e:
            futil.log(f"Error executing commands {command_ids}: {e}")
            return False


# Performance monitoring utilities
class PerformanceMonitor:
    """Monitor and log performance metrics"""

    def __init__(self):
        self.start_times = {}

    def start_timer(self, operation: str) -> None:
        """Start timing an operation"""
        self.start_times[operation] = time.time()

    def end_timer(self, operation: str) -> float:
        """End timing and return duration"""
        if operation in self.start_times:
            duration = time.time() - self.start_times[operation]
            del self.start_times[operation]
            futil.log(f"Performance: {operation} took {duration:.3f} seconds")
            return duration
        return 0.0

    @contextmanager
    def time_operation(self, operation: str):
        """Context manager for timing operations"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            futil.log(f"Performance: {operation} took {duration:.3f} seconds")


# Global performance monitor instance
perf_monitor = PerformanceMonitor()
