#!/usr/bin/env python3
"""
位置回调测试运行脚本

提供便捷的方式来运行位置回调相关的测试，包括精度测试、性能测试等。

用法：
    python run_position_callback_tests.py [test_type]
    
测试类型：
    - all: 运行所有位置回调测试
    - precision: 运行精度测试
    - performance: 运行性能测试
    - basic: 运行基础功能测试
    - stats: 运行统计功能测试
"""

import sys
import subprocess
import time
from pathlib import Path

def run_command(cmd: list) -> tuple[int, str, str]:
    """运行命令并返回结果"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def run_all_tests():
    """运行所有位置回调测试"""
    print("🎵 运行所有位置回调测试...")
    print("=" * 60)
    
    cmd = ["python", "-m", "pytest", "tests/test_position_callbacks.py", "-v", "--tb=short"]
    returncode, stdout, stderr = run_command(cmd)
    
    print(stdout)
    if stderr:
        print("警告或错误:")
        print(stderr)
    
    return returncode == 0

def run_precision_tests():
    """运行精度测试"""
    print("🎯 运行位置回调精度测试...")
    print("=" * 60)
    
    cmd = ["python", "-m", "pytest", 
           "tests/test_position_callbacks.py::TestCallbackPrecision", 
           "-v", "--tb=short"]
    returncode, stdout, stderr = run_command(cmd)
    
    print(stdout)
    if stderr:
        print("警告或错误:")
        print(stderr)
    
    return returncode == 0

def run_performance_tests():
    """运行性能测试"""
    print("⚡ 运行位置回调性能测试...")
    print("=" * 60)
    
    cmd = ["python", "-m", "pytest", 
           "tests/test_position_callbacks.py::TestPerformanceAndMemory", 
           "-v", "--tb=short"]
    returncode, stdout, stderr = run_command(cmd)
    
    print(stdout)
    if stderr:
        print("警告或错误:")
        print(stderr)
    
    return returncode == 0

def run_basic_tests():
    """运行基础功能测试"""
    print("🔧 运行基础位置回调功能测试...")
    print("=" * 60)
    
    cmd = ["python", "-m", "pytest", 
           "tests/test_position_callbacks.py::TestBasicPositionCallbacks", 
           "-v", "--tb=short"]
    returncode, stdout, stderr = run_command(cmd)
    
    print(stdout)
    if stderr:
        print("警告或错误:")
        print(stderr)
    
    return returncode == 0

def run_stats_tests():
    """运行统计功能测试"""
    print("📊 运行位置回调统计功能测试...")
    print("=" * 60)
    
    cmd = ["python", "-m", "pytest", 
           "tests/test_position_callbacks.py::TestCallbackStatistics", 
           "-v", "--tb=short"]
    returncode, stdout, stderr = run_command(cmd)
    
    print(stdout)
    if stderr:
        print("警告或错误:")
        print(stderr)
    
    return returncode == 0

def run_quick_test():
    """运行快速测试（仅基础功能）"""
    print("🚀 运行快速位置回调测试...")
    print("=" * 60)
    
    # 运行基础测试和统计测试（不包含实际音频播放）
    tests = [
        "tests/test_position_callbacks.py::TestBasicPositionCallbacks::test_callback_registration",
        "tests/test_position_callbacks.py::TestBasicPositionCallbacks::test_callback_removal",
        "tests/test_position_callbacks.py::TestGlobalPositionListeners::test_global_listener_registration",
        "tests/test_position_callbacks.py::TestErrorHandling::test_invalid_track_callback"
    ]
    
    cmd = ["python", "-m", "pytest"] + tests + ["-v", "--tb=short"]
    returncode, stdout, stderr = run_command(cmd)
    
    print(stdout)
    if stderr:
        print("警告或错误:")
        print(stderr)
    
    return returncode == 0

def print_usage():
    """打印使用说明"""
    print("位置回调测试运行脚本")
    print("=" * 60)
    print("用法: python run_position_callback_tests.py [test_type]")
    print()
    print("测试类型:")
    print("  all        - 运行所有位置回调测试（默认）")
    print("  precision  - 运行精度测试")
    print("  performance- 运行性能测试")
    print("  basic      - 运行基础功能测试")
    print("  stats      - 运行统计功能测试")
    print("  quick      - 运行快速测试（无音频播放）")
    print("  help       - 显示此帮助信息")
    print()
    print("示例:")
    print("  python run_position_callback_tests.py")
    print("  python run_position_callback_tests.py precision")
    print("  python run_position_callback_tests.py performance")

def main():
    """主函数"""
    test_type = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if test_type in ["help", "-h", "--help"]:
        print_usage()
        return
    
    start_time = time.time()
    success = False
    
    try:
        if test_type == "all":
            success = run_all_tests()
        elif test_type == "precision":
            success = run_precision_tests()
        elif test_type == "performance":
            success = run_performance_tests()
        elif test_type == "basic":
            success = run_basic_tests()
        elif test_type == "stats":
            success = run_stats_tests()
        elif test_type == "quick":
            success = run_quick_test()
        else:
            print(f"❌ 未知的测试类型: {test_type}")
            print_usage()
            return
    
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        return
    except Exception as e:
        print(f"❌ 测试运行出错: {e}")
        return
    
    elapsed_time = time.time() - start_time
    
    print()
    print("=" * 60)
    if success:
        print(f"✅ 位置回调测试完成！耗时: {elapsed_time:.1f}秒")
    else:
        print(f"❌ 位置回调测试失败！耗时: {elapsed_time:.1f}秒")
        sys.exit(1)

if __name__ == "__main__":
    main() 