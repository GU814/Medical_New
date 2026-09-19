"""
一键更新知识库工具 - 供医护人员使用
双击运行即可自动更新知识库
"""

import os
import sys
import subprocess
import shutil


def main():
    print("=" * 50)
    print("   医学问诊智能体 - 知识库更新工具")
    print("=" * 50)
    print()

    # 获取当前程序所在目录（兼容打包后的 exe）
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    knowledge_dir = os.path.join(base_dir, "data", "knowledge")
    chroma_dir = os.path.join(base_dir, "data", "chroma_db")
    init_script = os.path.join(base_dir, "init_knowledge.py")

    # 1. 检查知识库目录
    print(f"📁 知识库文档目录: {knowledge_dir}")
    print(f"📁 向量数据库目录: {chroma_dir}")
    print()

    if not os.path.exists(knowledge_dir):
        os.makedirs(knowledge_dir)
        print(f"⚠️ 请先将医学文档放入以下文件夹：")
        print(f"   {knowledge_dir}")
        print()
        input("📌 放入文档后按回车键继续...")

    # 2. 检查是否有文档
    doc_files = [f for f in os.listdir(knowledge_dir) if f.endswith(('.txt', '.md', '.pdf'))]
    if not doc_files:
        print("❌ 未找到任何文档（.txt / .md / .pdf）")
        print(f"   请将文档放入: {knowledge_dir}")
        input("按回车键退出...")
        return

    print(f"📄 找到 {len(doc_files)} 个文档:")
    for f in doc_files:
        print(f"   - {f}")
    print()

    # 3. 检查 Python 环境
    try:
        subprocess.run(["python", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("❌ 未找到 Python，请联系管理员安装 Python 3.8+")
        input("按回车键退出...")
        return

    # 4. 检查 init_knowledge.py 是否存在
    if not os.path.exists(init_script):
        print("❌ 缺少 init_knowledge.py 文件")
        print("   请联系管理员获取完整程序包")
        input("按回车键退出...")
        return

    # 5. 确认更新
    print("⚠️  即将更新知识库，这可能需要几分钟时间...")
    confirm = input("确认继续？(y/n): ")
    if confirm.lower() != 'y':
        print("已取消")
        input("按回车键退出...")
        return

    # 6. 执行知识库初始化
    print()
    print("🔄 正在更新知识库，请稍候...")
    print("-" * 50)

    try:
        result = subprocess.run(
            ["python", init_script],
            cwd=base_dir,
            capture_output=False,  # 显示实时输出
            text=True
        )

        print("-" * 50)

        if result.returncode == 0:
            print()
            print("✅ 知识库更新成功！")
            print("   请重启医学问诊智能体使新知识库生效。")
        else:
            print()
            print("❌ 知识库更新失败，请检查文档格式是否正确")

    except Exception as e:
        print(f"❌ 更新失败: {e}")

    print()
    input("按回车键退出...")


if __name__ == "__main__":
    main()