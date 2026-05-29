# New Assembly

[Back to PowerTools Assembly](../README.md)

The New Assembly command opens a docked quick-start palette that helps you populate a brand-new assembly. It appears automatically when you create a new, empty design with **Assembly** design intent, and can also be opened on demand from a toolbar button. From a single panel you can create external Part, Hybrid, or Assembly components in place, hand off to the Assembly Builder or Global Parameters commands, and insert components from a gallery of your currently-open or recently-used documents.

## What you can do

- **Create a component in place** — type a name, pick **Part**, **Hybrid**, or **Assembly** intent, and generate an external component in the active design with `addNewExternalComponent`. The chosen design intent is applied to the new component automatically.
- **Hand off to related commands** — open **Assembly Builder** to design a multi-level hierarchy, or **Global Parameters** to define a shared parameter set, without hunting for them on the toolbar. The palette hides while the handed-off command runs.
- **Insert an open document** — the **Open** tab shows a thumbnail gallery of your currently-open Part/Hybrid/Assembly documents. Click a card to insert that document into the active design as a referenced component (`addByInsert`).
- **Show only what you opened** — by default the Open tab lists only **top-level documents** (the ones you opened directly). Tick **Show referenced children** to also list the sub-assemblies and parts that Fusion loaded as references of an open assembly.
- **Insert a recent document** — the **Recent** tab shows a gallery of recently-touched Part/Hybrid/Assembly documents that are **not** currently open, backed by a small local cache that grows as you work.
- **Thumbnail previews everywhere** — each card renders the component's thumbnail. Thumbnails are cached on disk so the Recent gallery can show them even when the document is closed.
- Palette theme follows the Fusion UI theme — light, dark, or **match OS device theme** — and is correct on first paint.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- **Automatic launch** requires the active document to be **new (unsaved)**, **empty** (no timeline features, bodies, sketches, or child components), and to have **Assembly** design intent.
- **Insert from Open / Recent** requires the source document to be **saved** to an Autodesk Hub — `addByInsert` needs a cloud `DataFile`. Unsaved documents are not listed.

## How to use New Assembly

1. In Autodesk Fusion, create a new design with **File > New Design** and confirm the design intent is **Assembly**. The palette opens automatically docked to the right.
   - To open it manually at any time, select **New Assembly** in the **Assembly** tab's **Insert** panel (directly below **Insert STEP File**).
2. **To create a component:** enter a component name, choose **Part**, **Hybrid**, or **Assembly** from the dropdown, and select **New Component**. The external component is created in the active project's root folder and added to the active design.
3. **To insert an open document:** switch to the **Open** tab and click a thumbnail card. The document is inserted as a referenced component at the origin.
   - Tick **Show referenced children** if you also want to see (and insert) the sub-assemblies and parts loaded as references of an open assembly.
4. **To insert a recent document:** switch to the **Recent** tab and click a card. Recently-used documents that are not currently open are listed newest-first.
5. **To design a hierarchy or manage parameters:** select **Assembly Builder…** or **Global Parameters…**. The palette hides and the chosen command opens.

> **Note:** A document you insert during a palette session is removed from both galleries on the next refresh, so a second click cannot silently create a duplicate occurrence. Use the **↻** refresh button to re-scan open and recent documents at any time.

> **Note:** `addNewExternalComponent` requires an Autodesk Hub folder, so the active project's root folder is used as the destination for new components. You can move the generated documents afterward in the Data Panel.

## Access

| Method | Location |
|---|---|
| Automatic | Opens docked to the right when a **new, empty, Assembly-intent** design becomes active. |
| Manual | **Assembly** tab > **Insert** panel > **New Assembly** (below **Insert STEP File**). |

The palette docks to the right edge of the Fusion window. Closing it does not disable the automatic trigger — creating another new empty Assembly design opens it again.

## Architecture

New Assembly bridges an HTML/JS palette (running in Fusion's QT WebEngine) and the Fusion Python API. The palette hosts the three quick-start sections; the Python backend watches for new empty Assembly documents, enumerates open and recent documents, renders thumbnails, and performs component creation and insertion.

```mermaid
C4Context
  title New Assembly – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user starting a new assembly")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud documents inserted by reference and created in place")

  Rel(user, addin, "Creates a new empty Assembly; creates/inserts components from the palette")
  Rel(addin, fusion, "Watches documentActivated; creates and inserts components; renders thumbnails")
  Rel(fusion, hub, "Resolves DataFiles for insertion; stores created external components")
```

```mermaid
C4Container
  title New Assembly – Container View

  Person(user, "Design Engineer")

  Container_Boundary(cmd, "New Assembly command") {
    Container(python, "Python Backend", "commands/assemblyintent/entry.py", "Trigger gate, open/recent enumeration, thumbnails, create + insert")
    Container(palette, "HTML Palette", "resources/html/index.html", "Create form, Open/Recent tabbed galleries, theme")
    ContainerDb(init, "init.js", "Generated sidecar", "window.__ptInit: theme, doc name, open + recent docs")
    ContainerDb(recent, "recent_docs.json", "Local cache", "Recently-touched part/hybrid/assembly DataFile ids")
    ContainerDb(thumbs, "Thumbnail cache", "OS temp PNGs", "Per-DataFile thumbnails keyed by md5(id)")
  }

  System_Ext(fusion, "Fusion API", "adsk.core, adsk.fusion")

  Rel(user, palette, "Fills create form; clicks document cards; toggles Show referenced children")
  Rel(palette, python, "fusionSendData('createComponent' / 'insertDoc' / 'setShowChildren' / 'refresh')")
  Rel(python, palette, "sendInfoToHTML('setOpenDocs' / 'setRecentDocs' / 'setTheme')")
  Rel(python, init, "Writes state before palette open")
  Rel(python, recent, "Reads / appends recent entries")
  Rel(python, thumbs, "Renders + reads cached thumbnails")
  Rel(python, fusion, "addNewExternalComponent, addByInsert, createThumbnail")
```

```mermaid
C4Component
  title New Assembly – Python Backend

  Container_Boundary(python, "Python Backend") {
    Component(trigger, "documentActivated gate", "Trigger", "Pops palette once per new empty Assembly-intent doc; _palette_was_open_for dedup")
    Component(launch, "Launch button", "Toolbar", "PTAT-newAssembly control in Assembly > Insert; opens palette on demand")
    Component(state, "Palette state", "_gather_palette_state", "Theme, doc name, open docs, recent docs")
    Component(open, "Open enumerator", "_list_open_docs", "Top-level filter (documentReferences), dedup by id, excludes active/unsaved/inserted")
    Component(recent, "Recent enumerator", "_list_recent_docs", "Cache filtered to not-open + not-inserted; newest-first; dedup")
    Component(thumbs, "Thumbnail engine", "_thumbnail_for_open_doc", "Component.createThumbnail -> PNG cache -> data URL")
    Component(actions, "Action router", "_palette_incoming", "createComponent / insertDoc / setShowChildren / launch handoffs / refresh")
  }

  System_Ext(fusion, "Fusion API")

  Rel(trigger, state, "Builds state, shows palette")
  Rel(launch, state, "Builds state, shows palette")
  Rel(state, open, "Lists open documents")
  Rel(state, recent, "Lists recent documents")
  Rel(open, thumbs, "Renders thumbnails for open docs")
  Rel(actions, fusion, "addNewExternalComponent / addByInsert")
  Rel(open, fusion, "documentReferences (top-level test)")
```

### User flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Fusion
    participant Trigger as documentActivated gate
    participant Python as Python Backend
    participant Palette as HTML Palette

    User->>Fusion: File > New Design (Assembly intent)
    Fusion->>Trigger: documentActivated
    Trigger->>Trigger: Empty + unsaved + Assembly? not already shown?
    Trigger->>Python: _show_palette()
    Python->>Python: _gather_palette_state() (open + recent docs, thumbnails)
    Python->>Palette: write init.js + palettes.add()

    alt Create a component
        User->>Palette: Name + intent + New Component
        Palette->>Python: fusionSendData('createComponent')
        Python->>Fusion: addNewExternalComponent + designIntent
    else Insert an open / recent document
        opt Show referenced children
            User->>Palette: Toggle checkbox
            Palette->>Python: fusionSendData('setShowChildren')
            Python->>Palette: sendInfoToHTML('setOpenDocs')
        end
        User->>Palette: Click document card
        Palette->>Python: fusionSendData('insertDoc', dataFileId)
        Python->>Fusion: occurrences.addByInsert(dataFile)
    else Hand off
        User->>Palette: Assembly Builder… / Global Parameters…
        Palette->>Python: fusionSendData('launch…')
        Python->>Fusion: commandDefinition.execute()
    end

    Python->>Palette: sendInfoToHTML refresh (open + recent)
```

## Design decisions

### Why `documentActivated` instead of `documentOpened`?
`documentOpened` is not reliably emitted for **File > New** across Fusion builds (notably on macOS), while `documentActivated` fires consistently. It also fires on every tab switch, so a `_palette_was_open_for` gate (compared by Python object identity, not `id()`) suppresses re-popping the palette for a document it already handled. `documentOpened` is attached as a harmless backup when the running build exposes it.

### How are top-level documents told apart from referenced children?
Fusion answers this directly and instantly: `Document.documentReferences` raises *"Cannot get documentReferences of a non-top-level document"* for a reference-loaded child and returns the reference collection for a top-level document. The Open tab uses that in-memory check (no cloud round-trip) to show only the documents you opened directly. **Show referenced children** simply skips the filter.

### Why a generated `init.js` instead of a message handshake?
As with Assembly Builder, the palette loads asynchronously and `palettes.add()` rejects a query string on the URL. Writing `resources/html/init.js` (theme, document name, open docs, recent docs) **before** creating the palette lets the page read `window.__ptInit` synchronously and apply the correct theme before the first paint. A reopened palette is refreshed via `sendInfoToHTML` instead.

### Why render thumbnails with `Component.createThumbnail`?
The DataFile-backed cloud thumbnail did not resolve reliably in the target build. Rendering the live root component is dependable while a document is open, so thumbnails are generated for open documents and cached on disk (keyed by `md5(dataFileId)` in the OS temp folder). The Recent gallery — whose documents are closed and cannot be rendered — reuses whatever PNG was cached while the document was last open, falling back to a placeholder.

### Why a per-session "inserted" filter?
A document inserted from the palette is not "open in a tab," so the next refresh would re-list it under Recent and a second click would silently add a duplicate occurrence. Inserted DataFile ids are tracked for the current palette session and hidden from both galleries; the set is cleared each time the palette is opened so deliberate re-insertion is still possible in a fresh session.

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
