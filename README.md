# PowerTools New Documents tools for Fusion v1.0

Make working as a team, cloud data, and with assemblies more productive.

## Data Workflow

**[Create Assembly From Part](./docs/Assembly%20From.md)**

Create a new assembly with the active design document inserted as the first component.

**[New Document](./docs/New%20Document.md)**

Adds a QAT (Quick Access Toolbar) command to open a pallet to create new documents. Documents are auto-named and saved to the active project folder in Team.

---

## Manage Document References

**[Document References](./docs/Document%20References.md)**

Display a dialog with detailed information on the active documents references.

**[Reference Manager](./docs/Reference%20Manager.md)**

Show all references in the active document and their status. Provides utilities to work with references.

- Update all references or individually.
- Allow the selection of versions per reference.
- Open a reference in a new tab.

**[Get and Update](./docs/Get%20and%20Update.md)**

Typical x-ref assemblies will use assembly contexts to create associativity across parts. When new versions of x-refs are available one must load the new versions and then manually update the out of date contexts. Data Power Tools adds a QAT command to automatically get all latests and then update contexts.

**[Document Refresh](./docs/Document%20Refresh.md)**

When working in a team it can be necessary to reload the active assembly to load new versions created by other team members. Int he file menu the Refresh command will automatically close, get new versions and then reload the active document, saving you time and nuisance of doing this manually

---

## Information tools

**[Assembly Statistics](./docs/Assembly%20Statistics.md)**

Provide assembly information on the active document. Reports on components, references and joints.

**[Document Information](./docs/Document%20Information.md)**

Provide Cloud Data information on the active document. Reports on Hub, Project and Folder location including Fusion Manufacturing Cloud Data mode unique identifiers.

**[Document History](./docs/Document%20History.md)**

Show the history of the active document.

---

## UI Tweaks

**[Toggle Data Pane](./docs/Toggle%20Data%20Pane.md)**

Toggling the data pane is buried three level menu or a keyboard shortcut. This adds a button to the navbar to make toggling easier.

**[Recovery Save](./docs/Recovery%20Save.md)**

This creates an entry in the file menu to manually save a local recovery save.

---

## Productivity tools

**[Insert STEP](./docs/Insert%20Step.md)**

Browse the local device and insert a STEP file into the active document.