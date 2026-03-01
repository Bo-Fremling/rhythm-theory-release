# Rhythm Theory (RT) — Release Package

Author: Bo Fremling

This repository hosts release archives of the Rhythm Theory (RT) project.

## Download

Go to the Releases page and download the latest zip archive.

## Verify

1. Unzip the archive.
2. cd Release/
3. Run: bash verify_all.sh

If verification passes, the run will generate (among other artifacts):

* 00_TOP/LOCKS/SM_PARAM_INDEX/SM_29_REPORT.md
* out/SM29_PAGES.md

## What this is

A reproducible, review-friendly package with strict separation between:

* Core (no-facit / no-target influence)
* Compare/Overlay (reference values used only after Core)

See Release/START_HERE.md inside the archive for the canonical reading path.
