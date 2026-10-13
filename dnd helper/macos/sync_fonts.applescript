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
    set bundlePath to POSIX path of (path to me)
    set helperPath to bundlePath & "../../dnd_helper.py"
    set commandText to "python3 " & quoted form of helperPath & " --pause sync_fonts"
    repeat with droppedFolder in droppedFolders
        set folderPath to POSIX path of droppedFolder
        set commandText to commandText & " " & quoted form of folderPath
    end repeat
    tell application "Terminal"
        activate
        do script commandText
    end tell
end launchFolders
