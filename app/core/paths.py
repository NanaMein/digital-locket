from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FILES_DIR = PROJECT_ROOT.parent / "Locket Files"
VAULTS_ROOT = PROJECT_ROOT / "vaults"
OWNER_FILE = VAULTS_ROOT / ".owner.json"
INDEX_FILE = VAULTS_ROOT / ".index.json"
STATE_FILE = VAULTS_ROOT / ".state.json"