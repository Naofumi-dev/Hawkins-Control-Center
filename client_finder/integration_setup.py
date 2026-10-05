"""Private terminal credential entry, separate from browser resource selection."""
import getpass
import json
import os
import stat
import tempfile
import warnings
from pathlib import Path

from .configuration import ConfigurationError, default_config_path

FIELDS={
    "google":("GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","GMAIL_REFRESH_TOKEN"),
    "openrouter":("OPENROUTER_API_KEY",), "brave":("BRAVE_SEARCH_API_KEY",),
    "n8n":("HAWKINS_N8N_API_KEY","HAWKINS_N8N_OWNER_EMAIL"), "notion":("HAWKINS_NOTION_TOKEN",),
    "calcom":("HAWKINS_CALCOM_TOKEN",), "fathom":("HAWKINS_FATHOM_API_KEY",),
    "ghl":("HAWKINS_GHL_TOKEN",), "telegram":("CLIENT_FINDER_TELEGRAM_TOKEN","CLIENT_FINDER_TELEGRAM_BOT_ID"),
    "onlinejobs":("HAWKINS_ONLINEJOBS_PROFILE","HAWKINS_ONLINEJOBS_ACCOUNT_URL","HAWKINS_ONLINEJOBS_EMAIL_SELECTOR","HAWKINS_ONLINEJOBS_APPLIED_SELECTOR"),
}
ALLOWED={v for values in FIELDS.values() for v in values}


def private_path():
    return default_config_path().with_name("integrations.json")


def read_private(path):
    if not path.exists():
        return {}
    info=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
        raise ConfigurationError("Personal integration file must be owned and private (600)")
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or set(data)-ALLOWED or any(not isinstance(v,str) or not v or "\n" in v for v in data.values()):
        raise ConfigurationError("Unexpected private integration configuration")
    return data


def load_integration_environment():
    for key,value in read_private(private_path()).items():
        os.environ.setdefault(key,value)


def configure_integration(provider):
    if provider not in FIELDS:
        raise ConfigurationError("Choose one of: "+", ".join(FIELDS))
    path=private_path()
    data=read_private(path)
    print("Personal Hawkins only: armageddonvivas@gmail.com. Inputs are hidden.",flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error",getpass.GetPassWarning)
        values={key:getpass.getpass(key+": ").strip() for key in FIELDS[provider]}
    if any(not v or "\n" in v for v in values.values()):
        raise ConfigurationError("Every field is required; existing configuration was preserved")
    # Google identity is verified before persisting or reading any user data.
    if provider=="google":
        from .gmail import Gmail, request_json
        result=request_json("https://oauth2.googleapis.com/token",form={"client_id":values["GOOGLE_CLIENT_ID"],"client_secret":values["GOOGLE_CLIENT_SECRET"],"refresh_token":values["GMAIL_REFRESH_TOKEN"],"grant_type":"refresh_token"})
        Gmail(result.get("access_token","")).verify()
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.parent.is_symlink() or path.parent.stat().st_uid!=os.getuid() or stat.S_IMODE(path.parent.stat().st_mode)&0o077:
        raise ConfigurationError("Private setup directory must be owned and mode 700")
    data.update(values)
    fd,tmp=tempfile.mkstemp(prefix=".integrations-",dir=path.parent)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(data,f);f.write("\n");f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if Path(tmp).exists(): Path(tmp).unlink()
    print("Private values saved. Restart Hawkins, select personal resources in Connections, and run its verification. No workflow or sending was enabled.",flush=True)
