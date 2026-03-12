# Externalize

[Back to Readme](../README.md)

## Description

Convert one or more local (inline) components in the active assembly into external cloud documents and re-insert them at their original assembly positions.

In Fusion, components created directly inside an assembly are stored inline with the parent document. Externalizing a component saves it as a separate cloud document in the same hub folder as the active assembly, then replaces the inline occurrence with a linked reference — enabling reuse, independent versioning, and team sharing.

## Behavior

### Externalize a single component

Select a component occurrence in the canvas or browser and click **OK**. The command will:

1. Upload the component to the cloud folder containing the active document.
2. Delete the inline occurrence from the assembly.
3. Re-insert the newly created external document at the exact same position and orientation.

If a cloud file with the same name already exists in the folder, the existing file is reused and no new upload is performed.

### Externalize All

Enable the **Externalize All** checkbox to process every local first-level component in the active assembly automatically. The component selector is disabled when this option is active. Progress is shown in the Fusion progress bar in the lower-right corner of the window.

Any component whose upload fails is skipped and logged; successfully externalized components are still re-inserted. A summary message reports how many components were processed.

## Requirements

- A Fusion 3D Design must be active.
- The active document must already be saved to a Fusion Hub / Team folder. The command saves external components to the same folder as the active document.

## Access

Access to the **Externalize** command is from the **PowerTools Assembly** panel in the Design workspace.

[Back to Readme](../README.md)

IMA LLC Copyright
