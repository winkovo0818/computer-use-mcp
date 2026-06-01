use scripting additions

on run argv
    set maxDepth to 2
    if (count of argv) > 0 then set maxDepth to (item 1 of argv as number)
    
    tell application "System Events"
        set frontProc to first application process whose frontmost is true
        set appName to name of frontProc
        set appPID to unix id of frontProc
        set treeLines to my walkTree(frontProc, 0, maxDepth)
    end tell
    
    set output to "APP|" & appName & "|" & appPID & return & treeLines
    return output
end run

on walkTree(elem, depth, maxDepth)
    if depth > maxDepth then return ""
    
    set lineData to ""
    
    set elemRole to "?"
    set elemTitle to ""
    set elemX to 0
    set elemY to 0
    set elemW to 0
    set elemH to 0
    set elemEnabled to false
    
    try
        set r to role of elem
        set elemRole to r
    end try
    try
        set t to title of elem
        set elemTitle to t
    end try
    try
        set p to position of elem
        set elemX to (item 1 of p)
        set elemY to (item 2 of p)
    end try
    try
        set s to size of elem
        set elemW to (item 1 of s)
        set elemH to (item 2 of s)
    end try
    try
        set elemEnabled to enabled of elem
    end try
    
    set theLine to (depth as text) & "|" & (elemRole as text) & "|" & (elemTitle as text) & "|" & (elemX as text) & "|" & (elemY as text) & "|" & (elemW as text) & "|" & (elemH as text) & "|" & (elemEnabled as text)
    set lineData to theLine & return
    
    if depth < maxDepth then
        try
            set kids to every UI element of elem
            repeat with k in kids
                set childLines to my walkTree(k, depth + 1, maxDepth)
                if childLines is not "" then
                    set lineData to lineData & childLines
                end if
            end repeat
        end try
    end if
    
    return lineData
end walkTree
