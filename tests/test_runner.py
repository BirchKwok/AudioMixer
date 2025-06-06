#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试运行器
提供不同的测试套件和详细的测试报告
"""

import os
import sys
import subprocess
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any
import json


class TestRunner:
    """测试运行器类"""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.project_root = self.test_dir.parent
        self.results = {}
    
    def run_test_suite(self, suite: str, verbose: bool = True, 
                      generate_report: bool = True) -> Dict[str, Any]:
        """运行指定的测试套件"""
        
        test_suites = {
            'basic': [
                'test_basic_functionality.py',
            ],
            'matchering': [
                'test_matchering_integration.py',
            ],
            'advanced': [
                'test_advanced_features.py',
            ],
            'performance': [
                'test_benchmarks.py',
            ],
            'all': [
                'test_basic_functionality.py',
                'test_matchering_integration.py', 
                'test_advanced_features.py',
                'test_benchmarks.py',
            ]
        }
        
        if suite not in test_suites:
            raise ValueError(f"Unknown test suite: {suite}")
        
        test_files = test_suites[suite]
        
        print(f"🧪 运行测试套件: {suite}")
        print(f"📁 测试文件: {', '.join(test_files)}")
        print("=" * 60)
        
        results = {
            'suite': suite,
            'start_time': time.time(),
            'test_files': test_files,
            'results': {},
            'summary': {}
        }
        
        for test_file in test_files:
            print(f"\n📋 运行测试文件: {test_file}")
            print("-" * 40)
            
            file_result = self._run_pytest(test_file, verbose)
            results['results'][test_file] = file_result
        
        results['end_time'] = time.time()
        results['duration'] = results['end_time'] - results['start_time']
        
        # 生成汇总信息
        results['summary'] = self._generate_summary(results)
        
        if generate_report:
            self._generate_report(results)
        
        return results
    
    def _run_pytest(self, test_file: str, verbose: bool = True) -> Dict[str, Any]:
        """运行单个pytest文件"""
        file_path = self.test_dir / test_file
        
        if not file_path.exists():
            return {
                'success': False,
                'error': f"Test file not found: {test_file}",
                'duration': 0
            }
        
        # 构建pytest命令
        cmd = [
            sys.executable, '-m', 'pytest',
            str(file_path),
            '--tb=short',  # 简短的错误回溯
            '-x',          # 遇到第一个失败就停止
        ]
        
        if verbose:
            cmd.append('-v')
        
        # 添加性能相关参数
        if 'benchmark' in test_file.lower():
            cmd.extend([
                '--benchmark-only',
                '--benchmark-sort=mean'
            ])
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=300  # 5分钟超时
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            # 解析pytest输出
            output_lines = result.stdout.split('\n')
            error_lines = result.stderr.split('\n')
            
            # 查找测试结果摘要
            summary_line = ""
            for line in reversed(output_lines):
                if 'passed' in line or 'failed' in line or 'error' in line:
                    summary_line = line.strip()
                    break
            
            return {
                'success': result.returncode == 0,
                'returncode': result.returncode,
                'duration': duration,
                'summary': summary_line,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'output_lines': len(output_lines),
                'error_lines': len([l for l in error_lines if l.strip()])
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Test execution timed out',
                'duration': 300,
                'timeout': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Execution error: {str(e)}',
                'duration': time.time() - start_time
            }
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """生成测试结果汇总"""
        summary = {
            'total_files': len(results['test_files']),
            'passed_files': 0,
            'failed_files': 0,
            'total_duration': results['duration'],
            'status': 'PASSED'
        }
        
        for file_name, file_result in results['results'].items():
            if file_result.get('success', False):
                summary['passed_files'] += 1
            else:
                summary['failed_files'] += 1
                summary['status'] = 'FAILED'
        
        return summary
    
    def _generate_report(self, results: Dict[str, Any]):
        """生成详细的测试报告"""
        report_dir = self.test_dir / 'reports'
        report_dir.mkdir(exist_ok=True)
        
        # 生成JSON报告
        json_report = report_dir / f"test_report_{results['suite']}_{int(time.time())}.json"
        with open(json_report, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # 生成HTML报告
        html_report = report_dir / f"test_report_{results['suite']}_{int(time.time())}.html"
        self._generate_html_report(results, html_report)
        
        print(f"\n📊 测试报告已生成:")
        print(f"   JSON: {json_report}")
        print(f"   HTML: {html_report}")
    
    def _generate_html_report(self, results: Dict[str, Any], output_path: Path):
        """生成HTML格式的测试报告"""
        html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RealtimeMix 测试报告 - {suite}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 2em; }}
        .header .subtitle {{ margin: 5px 0 0 0; opacity: 0.9; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .summary-card {{ background: #f8f9fa; padding: 15px; border-radius: 6px; border-left: 4px solid #007bff; }}
        .summary-card.success {{ border-left-color: #28a745; }}
        .summary-card.failure {{ border-left-color: #dc3545; }}
        .summary-card h3 {{ margin: 0 0 10px 0; color: #333; }}
        .summary-card .value {{ font-size: 1.5em; font-weight: bold; color: #007bff; }}
        .test-file {{ margin-bottom: 20px; border: 1px solid #dee2e6; border-radius: 6px; overflow: hidden; }}
        .test-file-header {{ background: #e9ecef; padding: 15px; font-weight: bold; }}
        .test-file-header.success {{ background: #d4edda; color: #155724; }}
        .test-file-header.failure {{ background: #f8d7da; color: #721c24; }}
        .test-file-content {{ padding: 15px; }}
        .details {{ background: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 10px; }}
        .details pre {{ margin: 0; white-space: pre-wrap; word-wrap: break-word; }}
        .status-badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
        .status-badge.success {{ background: #d4edda; color: #155724; }}
        .status-badge.failure {{ background: #f8d7da; color: #721c24; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>RealtimeMix 测试报告</h1>
            <div class="subtitle">测试套件: {suite} | 生成时间: {timestamp}</div>
        </div>
        
        <div class="summary">
            <div class="summary-card {status_class}">
                <h3>总体状态</h3>
                <div class="value">{status}</div>
            </div>
            <div class="summary-card">
                <h3>测试文件</h3>
                <div class="value">{total_files}</div>
            </div>
            <div class="summary-card success">
                <h3>通过</h3>
                <div class="value">{passed_files}</div>
            </div>
            <div class="summary-card failure">
                <h3>失败</h3>
                <div class="value">{failed_files}</div>
            </div>
            <div class="summary-card">
                <h3>总耗时</h3>
                <div class="value">{duration:.1f}s</div>
            </div>
        </div>
        
        <div class="test-files">
            {test_files_html}
        </div>
        
        <div class="footer">
            <p>由 RealtimeMix 测试运行器生成</p>
        </div>
    </div>
</body>
</html>
        """
        
        # 生成测试文件详情HTML
        test_files_html = ""
        for file_name, file_result in results['results'].items():
            success = file_result.get('success', False)
            status_class = 'success' if success else 'failure'
            status_text = '通过' if success else '失败'
            
            file_html = f"""
            <div class="test-file">
                <div class="test-file-header {status_class}">
                    {file_name} 
                    <span class="status-badge {status_class}">{status_text}</span>
                    <span style="float: right;">耗时: {file_result.get('duration', 0):.2f}s</span>
                </div>
                <div class="test-file-content">
                    <p><strong>摘要:</strong> {file_result.get('summary', 'N/A')}</p>
                    {f'<p><strong>错误:</strong> {file_result.get("error", "")}</p>' if not success else ''}
                    <div class="details">
                        <strong>详细输出:</strong>
                        <pre>{file_result.get('stdout', '')[:1000]}{'...' if len(file_result.get('stdout', '')) > 1000 else ''}</pre>
                    </div>
                </div>
            </div>
            """
            test_files_html += file_html
        
        # 填充模板
        html_content = html_template.format(
            suite=results['suite'],
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            status=results['summary']['status'],
            status_class='success' if results['summary']['status'] == 'PASSED' else 'failure',
            total_files=results['summary']['total_files'],
            passed_files=results['summary']['passed_files'],
            failed_files=results['summary']['failed_files'],
            duration=results['summary']['total_duration'],
            test_files_html=test_files_html
        )
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def run_quick_check(self) -> bool:
        """运行快速检查，验证基本功能"""
        print("🚀 运行快速检查...")
        
        try:
            # 检查导入
            from realtimemix import AudioEngine
            print("✅ realtimemix 导入成功")
            
            # 检查基本初始化
            engine = AudioEngine()
            print("✅ AudioEngine 初始化成功")
            
            # 检查依赖项
            dependencies = ['numpy', 'soundfile', 'matchering']
            for dep in dependencies:
                try:
                    __import__(dep)
                    print(f"✅ {dep} 可用")
                except ImportError:
                    print(f"⚠️ {dep} 不可用")
            
            return True
            
        except Exception as e:
            print(f"❌ 快速检查失败: {e}")
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='RealtimeMix 测试运行器')
    parser.add_argument(
        'suite',
        choices=['basic', 'matchering', 'advanced', 'performance', 'all', 'quick'],
        help='要运行的测试套件'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='详细输出'
    )
    parser.add_argument(
        '--no-report',
        action='store_true',
        help='不生成测试报告'
    )
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    if args.suite == 'quick':
        # 运行快速检查
        success = runner.run_quick_check()
        sys.exit(0 if success else 1)
    else:
        # 运行测试套件
        try:
            results = runner.run_test_suite(
                args.suite,
                verbose=args.verbose,
                generate_report=not args.no_report
            )
            
            # 打印汇总结果
            print("\n" + "=" * 60)
            print("📊 测试结果汇总")
            print("=" * 60)
            print(f"测试套件: {results['suite']}")
            print(f"总体状态: {results['summary']['status']}")
            print(f"测试文件: {results['summary']['total_files']}")
            print(f"通过: {results['summary']['passed_files']}")
            print(f"失败: {results['summary']['failed_files']}")
            print(f"总耗时: {results['summary']['total_duration']:.1f}秒")
            
            # 根据结果设置退出码
            sys.exit(0 if results['summary']['status'] == 'PASSED' else 1)
            
        except Exception as e:
            print(f"❌ 测试运行失败: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main() 