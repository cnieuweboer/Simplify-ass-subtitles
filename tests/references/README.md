# Immutable release references

`simplify_ass_v177.py` preserves the production converter from commit
`1222d6e4573a8e69c4b5f174d72635ddcb853b35` byte for byte. It provides a stable
baseline for the v177 lifecycle scope audit and v178 normalization scope audit.
Behavioral checks continue to exercise the current production converter.

Do not edit a frozen engine to accommodate later changes. Earlier references
remain in the supplied local `test-data` folder.

`simplify_ass_v179.py` preserves commit
`775b98ec6b43ea511efb93b8eecfd1fda67cacd9` byte for byte. It freezes the
normalization scope audit and provides the staggered-fade timing baseline.
Behavioral checks use the current converter.

`simplify_ass_v180.py` preserves commit
`0eb1a2a71842ff9f33967f96b133844e52a888ad` byte for byte. It freezes the v180
fade-core scope audit and supplies the cross-lane synchronization baseline.
