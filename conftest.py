import os
import sys

# 确保项目根目录在 sys.path 中,使测试内 `import config` / `import app.*` 可解析
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
