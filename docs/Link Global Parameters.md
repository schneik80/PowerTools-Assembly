# Link Global Parameters

[Back to PowerTools Assembly](../README.md)

The Link Global Parameters command derives a parameter set from a shared parameters document into the active Autodesk Fusion document. It reads the parameter set created by the **Global Parameters** command from the `_Global Parameters` folder of the active project and inserts those parameters as a Derive feature in the active design.

## What you can do

- Browse all parameter sets available in the active project's `_Global Parameters` folder.
- Preview the parameters in a selected parameter set before committing.
- Derive the selected parameter set into the active document as favorite parameters so they are immediately available in Fusion's Favorites panel and in design expressions.
- Use cached project discovery data for faster startup, with lazy Hub scan fallback when needed.

## Prerequisites

- An Autodesk Fusion 3D Design must be active and saved to an Autodesk Hub project.
- At least one parameter set must exist in the project (created with the **Global Parameters** command).

## How to use Link Global Parameters

1. Open the Autodesk Fusion Design workspace with the target document active.
2. On the **Power Tools** panel, select **Link Global Parameters**.
3. In the **Parameter Set** dropdown, select the parameter set you want to link.
4. The preview table updates to show the parameters in the selected set:

   | Column | Description |
  | --- | --- |
   | Name | Parameter name as defined in the parameter set document |
   | Expression | Stored expression (e.g. `25.4 mm`) |
   | Unit | Unit string |
   | Comment | Optional comment (the `PT-globparm` sentinel prefix is stripped from the display) |

5. Confirm the parameters look correct, then select **OK**.

The command derives the parameter set document into the active design. All parameters marked as favorites in the parameter set document are inserted into the active document and appear in its Favorites panel.

> **Note:** The derive operation temporarily opens the parameter set document in the background and closes it when done. Focus returns to the active document automatically.

## Access


The **Link Global Parameters** command is on the **Power Tools** panel in the **Tools** tab of the Autodesk Fusion Design workspace.

## Refresh Global Parameters Cache

If parameter sets appear missing or out of date in the Link Global Parameters dialog, use the **Refresh Global Parameters Cache** command. This command forces a full scan of the Autodesk Hub project and rewrites the local caches for the active project, ensuring that all available parameter sets are discovered and up to date.

- **Location:** File → PowerTools Settings
- **When to use:** If you add, remove, or rename parameter sets outside of the add-in, or if the dropdown in Link Global Parameters does not show the latest sets.

After running this command, re-open the Link Global Parameters dialog to see the refreshed list of parameter sets.

## Architecture

The following diagrams show how the Link Global Parameters command interacts with the parameter set documents and the active design.

```mermaid
C4Context
  title Link Global Parameters – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user who wants to consume shared project parameters")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud project storage — hosts the _Global Parameters folder containing parameter set documents")

  Rel(user, addin, "Opens Link Global Parameters dialog; selects a parameter set")
  Rel(addin, fusion, "Lists Hub project folders; opens parameter set doc for preview; creates DeriveFeature in active design")
  Rel(fusion, hub, "Resolves _Global Parameters folder contents; opens and reads parameter set documents")
```

```mermaid
C4Component
  title Link Global Parameters – Component View

  Person(user, "Design Engineer")

  Component(cmd, "linkGlobalParameters/entry.py", "PowerTools Command", "Registers the toolbar button; builds the dialog; handles command lifecycle events")
  Component(folder_scan, "Project folder helpers", "Internal Module", "_find_global_params_folder / _list_param_docs — locate the _Global Parameters folder and enumerate available parameter set documents")
  Component(preview, "_load_preview", "Internal Module", "Opens the selected parameter set document in the background, reads its user parameters into the preview table, then closes the document")
  Component(derive, "_derive_into_active", "Internal Module", "Creates a DeriveFeature on the active document's rootComponent using the parameter set document as the source; sets isIncludeFavoriteParameters = True; removes physical geometry from the derive scope via excludedEntities")
  Component(safe_activate, "_safe_activate", "Internal Module", "Re-activates the original document after background open/close operations; guards against InternalValidationError")

  Component(api_design, "adsk.fusion.Design", "Fusion API", "rootComponent.features.deriveFeatures — createInput(), add()")
  Component(api_data, "adsk.core.Data / DataFolder", "Fusion API", "Browses project root to locate the _Global Parameters folder and its DataFile children")
  Component(api_docs, "adsk.core.Documents", "Fusion API", "open() for preview and derive; close() after each use")

  Rel(user, cmd, "Selects parameter set; confirms with OK")
  Rel(cmd, folder_scan, "Calls on dialog open to populate the Parameter Set dropdown")
  Rel(cmd, preview, "Calls on dropdown selection change to refresh the preview table")
  Rel(cmd, derive, "Calls on execute to derive parameters into the active document")
  Rel(derive, safe_activate, "Calls after closing the parameter set document")
  Rel(preview, api_docs, "Opens/closes parameter set document for read-only inspection")
  Rel(derive, api_design, "Creates DeriveFeature with isIncludeFavoriteParameters = True")
  Rel(derive, api_docs, "Opens parameter set document; kept open until DeriveFeature add() completes")
  Rel(folder_scan, api_data, "Iterates rootFolder.dataFolders and dataFiles")
```

## Caching and Discovery Logic

Link Global Parameters now uses a cache-first startup path:

1. Read `gp_docs_<project-key>.json` to populate the Parameter Set dropdown.
2. Read `gp_folder_<project-key>.json` for fast `_Global Parameters` folder resolution.
3. Attempt direct id-based `DataFile` resolve for initial preview.
4. Resolve dropdown selection by name using cache-id fast path first.
5. If a selected set is still unresolved (for example, partial in-memory map), force a full Hub refresh and retry.

This reduces command-created latency in large projects where root folder enumeration is expensive.

```mermaid
C4Component
  title Link Global Parameters – Cache-Aware Components

  Component(cmd, "Link Global Parameters command", "commands/linkGlobalParameters/entry.py", "Dialog lifecycle + derive execution")
  Component(docs_cache, "Docs cache", "gp_docs_<project-key>.json", "Cached parameter-set names and ids")
  Component(folder_cache, "Folder cache", "gp_folder_<project-key>.json", "Cached _Global Parameters folder id")
  Component(cache_id_resolve, "Cache-id resolver", "findFileById / findFolderById", "Best-effort direct resolve via Fusion API")
  Component(selected_resolver, "Selected-doc resolver", "_resolve_selected_data_file", "Resolves selected name via map, cache-id, then Hub refresh")
  Component(forced_refresh, "Forced Hub refresh", "_refresh_param_doc_map", "Full docs-map rebuild when selected set is unresolved")
  Component(derive_exec, "Derive executor", "_derive_into_active", "Derives favorite parameters into active design")

  Rel(cmd, docs_cache, "Read on open, write after scan")
  Rel(cmd, folder_cache, "Read on open, write after scan")
  Rel(cmd, cache_id_resolve, "Resolve initial preview doc by id")
  Rel(cmd, selected_resolver, "Invoke on inputChanged and execute")
  Rel(selected_resolver, forced_refresh, "Fallback when selected name not resolved")
  Rel(cmd, derive_exec, "Execute after selected set resolves to DataFile")
```

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Cmd as Link Global Parameters
  participant Cache as Local Cache
  participant Hub as Fusion Hub API

  User->>Cmd: Open command
  Cmd->>Cache: Read gp_docs for project
  alt Warm docs cache
    Cache-->>Cmd: names + ids
    Cmd->>Cmd: Build dropdown immediately
    Cmd->>Cache: Resolve first doc by cached id
  else Cache miss
    Cmd->>Hub: Scan _Global Parameters docs
    Hub-->>Cmd: DataFile map
    Cmd->>Cache: Write gp_docs
  end

  alt Initial preview doc resolved
    Cmd->>Hub: Open selected parameter-set doc
    Cmd->>Cmd: Populate preview table
    Cmd->>Hub: Close doc
  else Not resolved by id
    Cmd->>Cmd: Wait for dropdown change or execute
  end

  User->>Cmd: Change dropdown selection
  Cmd->>Cmd: Resolve selected name from map/cache-id
  alt Selected set unresolved
    Cmd->>Hub: Force full docs refresh
    Hub-->>Cmd: Return complete docs map
    Cmd->>Cache: Rewrite gp_docs
  end
  Cmd->>Hub: Open resolved selected doc
  Cmd->>Cmd: Refresh preview table
  Cmd->>Hub: Close doc

  User->>Cmd: Click OK
  Cmd->>Hub: Resolve selected DataFile (cache-id or refreshed map)
  Cmd->>Hub: Open selected parameter-set doc
  Cmd->>Cmd: Add DeriveFeature with favorite parameters
  Cmd->>Hub: Close doc and reactivate active design
```

```mermaid
sequenceDiagram
  actor User
  participant Dialog as Link Global Parameters Dialog
  participant Hub as Autodesk Hub (_Global Parameters folder)
  participant ActiveDoc as Active Fusion Document

  User->>Dialog: Open Link Global Parameters
  Dialog->>Hub: List parameter set documents in _Global Parameters folder
  Hub-->>Dialog: Return {name → DataFile} map
  Dialog->>User: Show Parameter Set dropdown populated with available sets
  User->>Dialog: Select a parameter set
  Dialog->>Hub: Open selected parameter set document (background, read-only)
  Hub-->>Dialog: Return parameter list
  Dialog->>Dialog: Populate preview table (Name, Expression, Unit, Comment)
  Dialog->>Hub: Close parameter set document
  User->>Dialog: Click OK
  Dialog->>Hub: Open parameter set document (for derive)
  Dialog->>ActiveDoc: Create DeriveFeature (isIncludeFavoriteParameters = True, no geometry)
  ActiveDoc-->>Dialog: Derive complete — favorite parameters now available
  Dialog->>Hub: Close parameter set document
  Dialog->>ActiveDoc: Re-activate active document
```
