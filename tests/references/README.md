# Immutable release references

`simplify_ass_v177.py` preserves the production converter from commit
`1222d6e4573a8e69c4b5f174d72635ddcb853b35` byte for byte. It provides a stable
baseline for the v177 lifecycle scope audit and v178 normalization scope audit.
Behavioral checks continue to exercise the current production converter.

Do not edit a frozen engine to accommodate later changes. Earlier references
remain in the supplied local `test-data` folder.
