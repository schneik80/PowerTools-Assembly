"""Shared caching and Hub-discovery utilities for PowerTools Global Parameters commands.

All three commands (globalParameters, linkGlobalParameters, refreshGlobalParametersCache)
use the same cache file formats.  This module owns those formats so they stay in sync.

Cache files (all written under add-in/cache/):
  gp_folder_<project-key>.json   — _Global Parameters folder id per project
  gp_docs_<project-key>.json     — parameter-set doc names and ids per project
  gp_params_<safe-doc-id>.json   — parameter sidecar written by globalParameters on save;
                                    lets linkGlobalParameters preview without opening the doc
"""

import adsk.core
import os
import json
import re

from . import general_utils as futil

app = adsk.core.Application.get()

# The Hub folder name that holds all parameter-set documents for a project.
GLOBAL_PARAMS_FOLDER_NAME = "_Global Parameters"

# add-in root is three levels up: lib/fusionAddInUtils/ → lib/ → add-in root
_ADDIN_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CACHE_FOLDER = os.path.join(_ADDIN_ROOT, "cache")


# ── Key and path helpers ──────────────────────────────────────────────────────


def project_cache_key(project) -> str:
    """Return a stable, filesystem-safe cache key for a project."""
    project_id = getattr(project, "id", None)
    raw_key = project_id if project_id else project.name
    return re.sub(r"[^\w\-]", "_", raw_key)


def global_params_folder_cache_path(project) -> str:
    """Return JSON path used to cache the Global Parameters folder identity."""
    return os.path.join(CACHE_FOLDER, f"gp_folder_{project_cache_key(project)}.json")


def param_docs_cache_path(project) -> str:
    """Return JSON path used to cache parameter-doc names/ids for quick UI load."""
    return os.path.join(CACHE_FOLDER, f"gp_docs_{project_cache_key(project)}.json")


def param_set_sidecar_path(data_file) -> str | None:
    """Return the path for a parameter-set content sidecar for *data_file*, or None."""
    doc_id = getattr(data_file, "id", None)
    if not doc_id:
        return None
    safe_id = re.sub(r"[^\w\-]", "_", doc_id)
    return os.path.join(CACHE_FOLDER, f"gp_params_{safe_id}.json")


# ── Folder cache ──────────────────────────────────────────────────────────────


def read_global_params_folder_cache(project, cmd_name: str) -> dict | None:
    """Read cached Global Parameters folder metadata for the given project."""
    path = global_params_folder_cache_path(project)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        if payload.get("projectName") != project.name:
            return None
        if not payload.get("folderId"):
            return None
        return payload
    except Exception:
        futil.log(f"{cmd_name}: failed to read folder cache — ignoring")
        return None


def write_global_params_folder_cache(project, folder, cmd_name: str) -> None:
    """Persist Global Parameters folder metadata for fast future lookup."""
    folder_id = getattr(folder, "id", None)
    if not folder_id:
        return
    payload = {
        "projectName": project.name,
        "projectKey": project_cache_key(project),
        "folderId": folder_id,
        "folderName": folder.name,
    }
    try:
        os.makedirs(CACHE_FOLDER, exist_ok=True)
        with open(global_params_folder_cache_path(project), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except Exception:
        futil.log(f"{cmd_name}: failed to write folder cache — ignoring")


def resolve_global_params_folder_from_cache(project, cmd_name: str):
    """Try to resolve the cached folder directly by id. Returns folder or None.

    Fusion APIs can vary by release/environment, so this attempts several
    best-effort direct lookup shapes before falling back to root folder scans.
    """
    cached = read_global_params_folder_cache(project, cmd_name)
    if cached is None:
        return None
    folder_id = cached["folderId"]

    # Preferred direct lookup path if available on this Fusion API surface.
    try:
        project_data = getattr(project, "data", None)
        find_folder_by_id = getattr(project_data, "findFolderById", None)
        if callable(find_folder_by_id):
            folder = find_folder_by_id(folder_id)
            if folder and folder.name == GLOBAL_PARAMS_FOLDER_NAME:
                return folder
    except Exception:
        pass

    # Alternate lookup path observed in some API contexts.
    try:
        app_data = getattr(app, "data", None)
        find_folder_by_id = getattr(app_data, "findFolderById", None)
        if callable(find_folder_by_id):
            folder = find_folder_by_id(folder_id)
            if folder and folder.name == GLOBAL_PARAMS_FOLDER_NAME:
                return folder
    except Exception:
        pass

    # Final attempt via DataFolders collection helper if supported.
    try:
        data_folders = project.rootFolder.dataFolders
        item_by_id = getattr(data_folders, "itemById", None)
        if callable(item_by_id):
            folder = item_by_id(folder_id)
            if folder and folder.name == GLOBAL_PARAMS_FOLDER_NAME:
                return folder
    except Exception:
        pass

    return None


def find_global_params_folder(project, cmd_name: str):
    """Return the '_Global Parameters' DataFolder in the project root, or None."""
    with futil.perf_timer("folder cache fast-path", f"{cmd_name}._find_param_folder"):
        cached_folder = resolve_global_params_folder_from_cache(project, cmd_name)
    if cached_folder is not None:
        return cached_folder

    root = project.rootFolder
    with futil.perf_timer(
        f"rootFolder.dataFolders scan (n={root.dataFolders.count})",
        f"{cmd_name}._find_param_folder",
    ):
        for i in range(root.dataFolders.count):
            folder = root.dataFolders.item(i)
            if folder.name == GLOBAL_PARAMS_FOLDER_NAME:
                write_global_params_folder_cache(project, folder, cmd_name)
                return folder
    return None


# ── Docs cache ────────────────────────────────────────────────────────────────


def read_param_docs_cache(project, cmd_name: str) -> list[dict]:
    """Return cached parameter-doc entries [{name, id}] for a project."""
    path = param_docs_cache_path(project)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        if payload.get("projectName") != project.name:
            return []
        docs = payload.get("docs", [])
        entries = [
            {"name": d.get("name", ""), "id": d.get("id", "")}
            for d in docs
            if d.get("name")
        ]
        # Remove duplicate names while preserving order
        seen: set = set()
        deduped = []
        for entry in entries:
            name = entry["name"]
            if name not in seen:
                seen.add(name)
                deduped.append(entry)
        return deduped
    except Exception:
        futil.log(f"{cmd_name}: failed to read docs cache — ignoring")
        return []


def write_param_docs_cache(project, doc_map: dict, cmd_name: str) -> None:
    """Persist parameter-doc names/ids for fast startup dropdown population."""
    docs = [
        {"name": name, "id": getattr(data_file, "id", "")}
        for name, data_file in doc_map.items()
    ]
    payload = {
        "projectName": project.name,
        "projectKey": project_cache_key(project),
        "docs": docs,
    }
    try:
        os.makedirs(CACHE_FOLDER, exist_ok=True)
        with open(param_docs_cache_path(project), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except Exception:
        futil.log(f"{cmd_name}: failed to write docs cache — ignoring")


def upsert_param_docs_cache_entry(
    project, doc_name: str, doc_id: str, cmd_name: str
) -> None:
    """Insert or update a single parameter-set entry in the project docs cache."""
    if not doc_name:
        return
    path = param_docs_cache_path(project)
    docs = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
            if payload.get("projectName") == project.name:
                docs = payload.get("docs", [])
    except Exception:
        docs = []

    updated = []
    replaced = False
    for entry in docs:
        if entry.get("name") == doc_name:
            updated.append({"name": doc_name, "id": doc_id or entry.get("id", "")})
            replaced = True
        elif entry.get("name"):
            updated.append({"name": entry.get("name", ""), "id": entry.get("id", "")})
    if not replaced:
        updated.append({"name": doc_name, "id": doc_id or ""})

    new_payload = {
        "projectName": project.name,
        "projectKey": project_cache_key(project),
        "docs": updated,
    }
    try:
        os.makedirs(CACHE_FOLDER, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(new_payload, fh, indent=2)
    except Exception:
        futil.log(f"{cmd_name}: failed to upsert docs cache entry — ignoring")


def list_param_docs(project, cmd_name: str) -> dict:
    """Return {doc_name: DataFile} for all docs in the '_Global Parameters' folder."""
    with futil.perf_timer("find_global_params_folder", f"{cmd_name}._list_param_docs"):
        folder = find_global_params_folder(project, cmd_name)
    if folder is None:
        return {}
    result = {}
    with futil.perf_timer(
        f"dataFiles scan (n={folder.dataFiles.count})", f"{cmd_name}._list_param_docs"
    ):
        for i in range(folder.dataFiles.count):
            df = folder.dataFiles.item(i)
            result[df.name] = df
    write_param_docs_cache(project, result, cmd_name)
    return result


# ── Parameter-set sidecar ─────────────────────────────────────────────────────


def write_param_set_sidecar(data_file, parameters: list, cmd_name: str) -> None:
    """Write a JSON sidecar for a saved parameter set document.

    The sidecar lets linkGlobalParameters preview parameters without calling
    app.documents.open(), which switches the active document and is unreliable
    inside a running command dialog.

    *parameters* is the list of dicts produced by globalParameters._collect_rows()
    with keys: name, value (float), unit, comment (without PT-globparm prefix).
    """
    path = param_set_sidecar_path(data_file)
    if path is None:
        return
    records = [
        {
            "name": p["name"],
            "expression": f"{p['value']} {p['unit']}",
            "unit": p["unit"],
            "comment": p.get("comment", ""),
        }
        for p in parameters
    ]
    payload = {
        "docId": getattr(data_file, "id", ""),
        "docName": getattr(data_file, "name", ""),
        "parameters": records,
    }
    try:
        os.makedirs(CACHE_FOLDER, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        futil.log(f"{cmd_name}: param set sidecar written → {path}")
    except Exception:
        futil.log(f"{cmd_name}: failed to write param set sidecar — ignoring")


def read_param_set_sidecar(data_file) -> list[dict] | None:
    """Return cached parameter records [{name, expression, unit, comment}] for
    *data_file*, or None if no valid sidecar exists.

    Returns None (instead of []) when the sidecar is absent or unreadable so
    callers can distinguish 'no cache' from 'empty parameter set'.
    """
    path = param_set_sidecar_path(data_file)
    if path is None or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        # Guard against a stale sidecar that happens to share a safe_id
        cached_id = payload.get("docId", "")
        file_id = getattr(data_file, "id", "")
        if cached_id and file_id and cached_id != file_id:
            return None
        return payload.get("parameters", [])
    except Exception:
        return None


# ── General helpers ───────────────────────────────────────────────────────────


def get_active_project(cmd_name: str):
    """Return app.data.activeProject, or None if unavailable or on failure."""
    try:
        project = app.data.activeProject
        return project if project else None
    except Exception:
        futil.log(f"{cmd_name}: could not retrieve active project — ignoring")
        return None


def safe_activate(doc: adsk.core.Document, cmd_name: str) -> None:
    """Re-activate *doc* only when it is not already the active document.

    Calling activate() on an already-active document raises InternalValidationError
    in some Fusion builds, so we guard with an identity check first.
    """
    try:
        if doc.isValid and app.activeDocument != doc:
            doc.activate()
    except Exception:
        futil.log(f"{cmd_name}: could not re-activate original document — ignoring")
