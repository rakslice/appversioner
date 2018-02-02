import array

import ctypes

# from https://stackoverflow.com/questions/580924/python-windows-file-version-attribute


def get_file_info(filename, info):
    """
    Extract information from a file.
    """
    # Get size needed for buffer (0 if no info)
    size = ctypes.windll.version.GetFileVersionInfoSizeA(filename, None)
    # If no info in file -> empty string
    if not size:
        return ''
    # Create buffer
    res = ctypes.create_string_buffer(size)
    # Load file informations into buffer res
    ctypes.windll.version.GetFileVersionInfoA(filename, None, size, res)
    r = ctypes.c_uint()
    l = ctypes.c_uint()
    # Look for codepages
    ctypes.windll.version.VerQueryValueA(res, '\\VarFileInfo\\Translation',
                                         ctypes.byref(r), ctypes.byref(l))
    # If no codepage -> empty string
    if not l.value:
        return ''
    # Take the first codepage (what else ?)
    codepages = array.array('H', ctypes.string_at(r.value, l.value))
    codepage = tuple(codepages[:2].tolist())
    # Extract information
    ctypes.windll.version.VerQueryValueA(res, ('\\StringFileInfo\\%04x%04x\\'
                                        + info) % codepage,
                                         ctypes.byref(r), ctypes.byref(l))
    return ctypes.string_at(r.value, l.value)
