# appversioner #

This is a script that checks currently installed Windows program versions against the newest versions listed on the web.

For each program, it reads the version tag of the specified file to find the installed version, and fetches a specified web page and looks for a version number in the specified part of the page to find the latest available version.

It takes a JSON-formatted configuration file `apps.json`. This file has an array with an object entry for each program file to check. See the details and example below.

By default the script shows only the programs where a newer version is available; run with `-a` to show the versions of programs that are already up to date as well.

## Per-app settings ##

| Setting    |  Description |
| ---------- | ------------ |
| `dir_env`  | Place to look for the program under, in the form of an environment variable, for instance `APPDATA`, `ProgramW6432`, `ProgramFiles(x86)`, `USERPROFILE`. See [the handy list in the Windows Defender docs](https://www.microsoft.com/en-us/wdsi/help/folder-variables) for more).  You can use the special value `ProgramFiles` to look in both `ProgramW6432` and `ProgramFiles(x86)` (and warn if there is a file in both locations).  |
| `program_file` | Path of the program file within that place |
| `website_url`  | Web page to get the latest available version number from |
| `selector`     | [CSS selector](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Selectors) that gets the part of the page with the version number |
| `converter`    | What format the version number for this program is in, for finding the version number and choosing how to compare them. See choices below. Default is `"none"` |
| `version_attr` | What version field to use out of the file's version tag. Default is `"FileVersion"`. See the Remarks section of [the Windows API docs for VerQueryValue ](https://msdn.microsoft.com/en-us/library/windows/desktop/ms647464%28v=vs.85%29.aspx)to get a list of possible values | 

Version number formats for use with `converter`: 
- `"float"`: a two part number with a dot (`x.y`). Treat as a decimal number for comparisons (e.g. `1.10` is older than `1.9`)
- `"two"`: a two-part dotted section number (`x.y`). Compare sections in order (e.g. `1.9` is older than `1.10`). 
- `"three"`: a three-part dotted section number (`x.y.z`).
- `"multi"`: a three-or-more-part dotted section number (`x.y.z`, `x.y.z.w`, ...) 
- `"none"`: ignore the specifics of where the digits are and just version strings to be in alphabetical order

## Example ##

Here's an example `apps.json` file that checks my 32-bit WinSCP install:

	[
	    {
	    "dir_env": "ProgramFiles(x86)",
	    "program_file": "WinSCP\\WinSCP.exe",
	    "website_url": "https://winscp.net/eng/download.php",
	    "selector": "main a",
	    "converter": "three"
	    }
	]
