Scripts to simplify ass/ssa subtitles, embedded in mkv files.
Intended usecase is for playing videos on tv's or other weaker devices, that can struggle with complex subtitles.
And some additional bat files to set/unset default and forced subtitle tracks in mkv files.

Copy any of the bat files, with corresponding ps1 and py files, to a folder containing you mkv video files. And double click the bat file. 

Note that the "Partial: attempts to preserve manageable vector drawings" option is intended for subtitles with actual vector drawings. It makes many assumptions. And I have only have 1 series with background vector drawings in its subtitles. Ymmv.

"remove_simplified_subtitles.bat" only works when existing subtitles were not replaced.

Requires:MKVtoolnix, Python, Pillow, fonttools

use "python -m pip install Pillow fonttools" to install pillow and fonttools
