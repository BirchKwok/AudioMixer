#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RealtimeMix 测试套件启动器
提供便捷的测试运行入口
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入测试运行器
from tests.test_runner import TestRunner, main

def quick_demo():
    """快速演示测试套件"""
    print("🎵 RealtimeMix 测试套件演示")
    print("=" * 50)
    
    runner = TestRunner()
    
    # 1. 运行快速检查
    print("\n1️⃣ 快速环境检查...")
    success = runner.run_quick_check()
    
    if not success:
        print("❌ 环境检查失败，请检查依赖项安装")
        return False
    
    print("\n✅ 环境检查通过!")
    
    # 2. 询问用户要运行哪些测试
    print("\n2️⃣ 选择要运行的测试套件:")
    print("   [1] 基本功能测试 (推荐)")
    print("   [2] Matchering 集成测试")
    print("   [3] 高级功能测试") 
    print("   [4] 性能基准测试")
    print("   [5] 运行所有测试")
    print("   [0] 退出")
    
    try:
        choice = input("\n请选择 (1-5, 0退出): ").strip()
        
        suite_map = {
            '1': 'basic',
            '2': 'matchering', 
            '3': 'advanced',
            '4': 'performance',
            '5': 'all'
        }
        
        if choice == '0':
            print("👋 退出测试")
            return True
        elif choice in suite_map:
            suite = suite_map[choice]
            print(f"\n3️⃣ 运行 {suite} 测试套件...")
            
            # 运行选择的测试套件
            results = runner.run_test_suite(
                suite=suite,
                verbose=True,
                generate_report=True
            )
            
            # 显示结果
            print(f"\n🎯 测试完成!")
            print(f"状态: {results['summary']['status']}")
            print(f"通过: {results['summary']['passed_files']}/{results['summary']['total_files']}")
            print(f"耗时: {results['summary']['total_duration']:.1f}秒")
            
            return results['summary']['status'] == 'PASSED'
        else:
            print("❌ 无效选择")
            return False
            
    except KeyboardInterrupt:
        print("\n\n👋 用户中断测试")
        return False
    except Exception as e:
        print(f"\n❌ 测试运行出错: {e}")
        return False

def print_usage():
    """打印使用说明"""
    print("""
🧪 RealtimeMix 测试套件使用说明

基本用法:
    python run_tests.py                    # 交互式测试选择
    python run_tests.py quick             # 快速环境检查
    python run_tests.py basic             # 基本功能测试
    python run_tests.py matchering        # Matchering 集成测试
    python run_tests.py advanced          # 高级功能测试
    python run_tests.py performance       # 性能基准测试
    python run_tests.py all               # 运行所有测试

高级选项:
    python run_tests.py all --verbose     # 详细输出
    python run_tests.py basic --no-report # 不生成报告

直接使用 pytest:
    pytest tests/                         # 运行所有测试
    pytest tests/test_basic_functionality.py  # 运行特定测试文件
    pytest tests/ -v                      # 详细输出
    pytest tests/ -k "test_engine"        # 运行包含特定关键字的测试

环境要求:
    - Python >= 3.7
    - realtimemix 库
    - 测试依赖 (pip install -r tests/requirements-test.txt)
    - 音频输出设备

更多信息请查看: tests/README.md
    """)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # 没有参数，运行交互式演示
        success = quick_demo()
        sys.exit(0 if success else 1)
    elif sys.argv[1] in ['-h', '--help', 'help']:
        # 显示帮助
        print_usage()
        sys.exit(0)
    else:
        # 有参数，传递给测试运行器主函数
        main() 