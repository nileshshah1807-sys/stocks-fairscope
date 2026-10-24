"""OS-keychain-first encrypted local secret storage and restrictive file permissions."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

SERVICE="DrNileshShahStocksFairScope"
MASTER_NAME="local-encryption-master-key"

def protect_path(path,mode=0o600):
    try:os.chmod(path,mode)
    except OSError:pass

def protect_directory(path):
    path=Path(path);path.mkdir(parents=True,exist_ok=True);protect_path(path,0o700);return path

def data_directory()->Path:
    """Per-user folder holding every FairScope database, key, and log."""
    if os.name=="nt":root=Path(os.environ.get("LOCALAPPDATA",Path.home()))/"DR NILESH SHAH"/"Stocks FairScope"
    elif sys.platform=="darwin":root=Path.home()/"Library"/"Application Support"/"DR NILESH SHAH Stocks FairScope"
    else:root=Path(os.environ.get("XDG_DATA_HOME",Path.home()/".local"/"share"))/"stocks-fairscope"
    return protect_directory(root)

class SecureStorage:
    def __init__(self,root):
        self.root=protect_directory(root);self.key_path=self.root/".fairscope.key";self.secret_path=self.root/"secure_settings.json";self.backend=""
        self.cipher=Fernet(self._load_key())
    def _keyring(self):
        try:
            import keyring
            return keyring
        except Exception:return None
    def _load_key(self):
        keyring=self._keyring()
        if keyring:
            try:
                stored=keyring.get_password(SERVICE,MASTER_NAME)
                if stored:self.backend="Operating-system keychain";return stored.encode()
                key=Fernet.generate_key();keyring.set_password(SERVICE,MASTER_NAME,key.decode());self.backend="Operating-system keychain";return key
            except Exception:pass
        if self.key_path.exists():
            key=self.key_path.read_bytes().strip();protect_path(self.key_path);self.backend="Protected local key file";return key
        key=Fernet.generate_key();self.key_path.write_bytes(key);protect_path(self.key_path);self.backend="Protected local key file";return key
    def _read(self):
        if not self.secret_path.exists():return {}
        try:return json.loads(self.secret_path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):return {}
    def _write(self,data):self.secret_path.write_text(json.dumps(data,indent=2),encoding="utf-8");protect_path(self.secret_path)
    def set_secret(self,name,value):
        data=self._read()
        if value:data[name]=self.cipher.encrypt(str(value).encode()).decode()
        else:data.pop(name,None)
        self._write(data)
    def get_secret(self,name,default=""):
        token=self._read().get(name)
        if not token:return default
        try:return self.cipher.decrypt(token.encode()).decode()
        except (InvalidToken,ValueError):return default
    def delete_secret(self,name):self.set_secret(name,"")
