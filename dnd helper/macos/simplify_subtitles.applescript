on open droppedFolders
    my launchFolders(droppedFolders)
end open

on run
    try
        set droppedFolders to {(choose folder with prompt "Choose a folder containing MKVs")}
        my launchFolders(droppedFolders)
    on error number -128
        return
    end try
end run

on launchFolders(droppedFolders)
    repeat with droppedFolder in droppedFolders
        set droppedInfo to info for droppedFolder
        if not folder of droppedInfo and name extension of droppedInfo is not "mkv" then
            display alert "Drop MKV files or folders containing MKVs."
            return
        end if
    end repeat
    set bundlePath to POSIX path of (path to me)
    set scriptPath to bundlePath & "../simplify_subtitles.py"
    set commandText to ""
    repeat with droppedFolder in droppedFolders
        set folderPath to POSIX path of droppedFolder
        set commandText to commandText & "python3 " & quoted form of scriptPath & " " & quoted form of folderPath & "; "
    end repeat
    set commandText to commandText & "printf '\\nPress Enter to close: '; read -r dnd_answer"
    tell application "Terminal"
        activate
        do script commandText
    end tell
end launchFolders
