import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import logging
import git
from config import WORKSPACE_DIR

logger = logging.getLogger("GitVCS")

class GitVCS:
    def __init__(self, repo_dir: Path = WORKSPACE_DIR):
        self.repo_dir = repo_dir
        self.repo = self._ensure_repo()

    def _ensure_repo(self):
        try:
            return git.Repo(self.repo_dir)
        except git.exc.InvalidGitRepositoryError:
            try:
                logger.info(f"偵測到工作區未建立 Git，自動初始化倉庫: {self.repo_dir}")
                return git.Repo.init(self.repo_dir)
            except Exception as e:
                logger.warning(f"Git 初始化失敗: {e}")
                return None
        except Exception as e:
            logger.warning(f"無法載入 Git 倉庫: {e}")
            return None

    def commit_changes(self, message: str) -> bool:
        if not self.repo:
            self.repo = self._ensure_repo()
            if not self.repo:
                return False

        try:
            self.repo.git.add(A=True)
            # 若無實質變更則不 commit
            if not self.repo.is_dirty(untracked_files=True):
                return True
            self.repo.index.commit(message)
            return True
        except Exception as e:
            logger.warning(f"Git 版本提交略過: {e}")
            return False