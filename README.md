Scripts to simplify ass/ssa subtitles, embedded in mkv files.
Intended usecase is for playing videos on tv's or other weaker devices.

Copy all files to the folder with mkv files and run "simplify_ass.bat".
The changed mkv files are placed in an "output" subfolder.

Note that the "Partial: attempts to preserve manageable vector drawings" option is intended for subtitles with actual vector drawings. It makes many assumptions. And I have only have 1 series background vector drawings as part of the subtitles. It makes them usable for that one series but ymmv.

Use "remove_simplified_subtitles.bat" to remove the simplified subtitles. Only works when existing subtitles were not replaced.

Use "no_forced_subtitles.bat" to unset any forced subtitle track.

Requires installed MKVtoolnix.
