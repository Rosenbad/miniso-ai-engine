# ==============================================================================
# pytest 全局配置 - 确保 backend/ 目录在 sys.path 中
# ==============================================================================
# 使 `from shared.xxx import ...` 等绝对导入在测试中可用
# ==============================================================================

import os
import sys

# 将 backend/ 目录加入 sys.path (conftest.py 所在目录)
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
