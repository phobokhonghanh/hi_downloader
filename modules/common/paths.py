import os
import platform

def get_app_dir(dir_type: str = "data") -> str:
    """
    Get OS-specific user data, config, cache, or log directory for 'hi_downloader'.
    
    dir_type can be:
      - 'config': for settings (config.json, proxies.txt)
      - 'data': for general persistent data
      - 'cache': for translation caches
      - 'temp': for dynamic temporary files
      
    Directories follow standard OS patterns:
      - Windows: %LOCALAPPDATA%/hi_downloader
      - macOS: ~/Library/Application Support/hi_downloader
      - Linux: ~/.config/hi_downloader (config) / ~/.local/share/hi_downloader (others)
    """
    app_name = "hi_downloader"
    system = platform.system()
    home = os.path.expanduser("~")

    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = os.path.join(home, "AppData", "Local")
        base = os.path.join(local_app_data, app_name)
    elif system == "Darwin":
        base = os.path.join(home, "Library", "Application Support", app_name)
    else:
        # Linux / XDG
        if dir_type == "config":
            xdg_config = os.environ.get("XDG_CONFIG_HOME")
            if not xdg_config:
                xdg_config = os.path.join(home, ".config")
            base = os.path.join(xdg_config, app_name)
        else:
            xdg_data = os.environ.get("XDG_DATA_HOME")
            if not xdg_data:
                xdg_data = os.path.join(home, ".local", "share")
            base = os.path.join(xdg_data, app_name)

    # Attach type subdirectories
    if dir_type == "log":
        path = os.path.join(base, "logs")
    elif dir_type == "cache":
        path = os.path.join(base, "cache")
    elif dir_type == "temp":
        path = os.path.join(base, "temp")
    else:
        path = base

    return path
