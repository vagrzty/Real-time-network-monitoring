import subprocess
import datetime
import platform
import sys
import os
import time
import re
import locale
import threading
import queue

def get_system_encoding():
    """可靠获取系统编码"""
    try:
        enc = locale.getpreferredencoding()
        if enc and enc.lower() != 'ascii':
            return enc
        if platform.system().lower() == "windows":
            import ctypes
            return 'cp' + str(ctypes.windll.kernel32.GetACP())
        return sys.getfilesystemencoding() or 'utf-8'
    except:
        return 'utf-8'

def read_output(stream, q, encoding):
    """专门用于读取子进程输出的线程函数"""
    try:
        while True:
            line = stream.readline()
            if not line:
                break
            try:
                # 尝试用指定编码解码
                decoded_line = line.decode(encoding, errors='replace').rstrip()
            except:
                try:
                    # 备用编码
                    decoded_line = line.decode('gbk', errors='replace').rstrip()
                except:
                    decoded_line = line.decode('latin-1', errors='replace').rstrip()
            q.put(decoded_line)
    except Exception as e:
        q.put(f"READ_ERROR: {str(e)}")
    finally:
        q.put(None)  # 表示流已结束

def main():
    print("="*60)
    print("【网络监控工具 Qwen3-235B-A22B-2507编写】")
    print(f"操作系统: {platform.system()} {platform.release()}")
    
    system_encoding = get_system_encoding()
    print(f"检测到系统编码: {system_encoding}")
    
    # 检查ping命令
    try:
        test_ping = subprocess.run(
            ['ping', '-n', '1', '8.8.8.8'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system().lower() == "windows" else 0
        )
        if test_ping.returncode != 0:
            print(f"\033[91m⚠️ 警告: ping命令测试失败! 返回码: {test_ping.returncode}\033[0m")
            print("错误输出:", test_ping.stderr.decode(system_encoding, errors='replace'))
        else:
            print("✅ ping命令测试成功")
    except Exception as e:
        print(f"\033[91m❌ 严重错误: 无法执行ping命令 - {str(e)}\033[0m")
        sys.exit(1)
    
    website = sys.argv[1] if len(sys.argv) > 1 else "8.8.8.8"
    log_file = "network_monitor.log"
    
    print(f"\n【开始监控】目标: {website}")
    print(f"日志文件: {os.path.abspath(log_file)}")
    print("按 Ctrl+C 停止监控 | 成功响应显示为绿色，超时显示为黄色")
    print("="*60)
    
    # 创建日志文件
    start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, 'a', encoding=system_encoding) as f:
            f.write(f"\n===== 开始监控 {website} 于 {start_time} =====\n")
            f.write(f"操作系统: {platform.system()} {platform.release()}\n")
            f.write(f"系统编码: {system_encoding}\n")
    except Exception as e:
        print(f"\033[91m❌ 无法创建日志文件: {str(e)}\033[0m")
        log_file = None
    
    try:
        # 启动ping进程 - 关键：使用二进制模式避免编码问题
        ping_cmd = ['ping', '-t', website]
        print(f"执行命令: {' '.join(ping_cmd)}")
        
        ping_process = subprocess.Popen(
            ping_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        print(f"✅ Ping进程已启动 (PID: {ping_process.pid})")
        print("正在监控网络连接...\n")
        
        # 使用线程安全队列处理输出
        stdout_queue = queue.Queue()
        stderr_queue = queue.Queue()
        
        # 启动读取线程
        stdout_thread = threading.Thread(
            target=read_output, 
            args=(ping_process.stdout, stdout_queue, system_encoding),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=read_output, 
            args=(ping_process.stderr, stderr_queue, system_encoding),
            daemon=True
        )
        
        stdout_thread.start()
        stderr_thread.start()
        
        # 实时处理队列中的输出
        while True:
            # 处理标准输出
            try:
                while True:
                    stdout_line = stdout_queue.get_nowait()
                    if stdout_line is None:  # 流结束标志
                        break
                    if stdout_line.startswith("READ_ERROR:"):
                        print(f"\033[91m❌ 读取错误: {stdout_line[12:]}\033[0m")
                        continue
                    
                    current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    
                    # 检查ping状态
                    if ("TTL" in stdout_line or "ttl" in stdout_line or 
                        ("来自" in stdout_line and "的回复" in stdout_line)):
                        color_code = "\033[92m"  # 绿色
                        status = " ✓ 成功"
                    elif "超时" in stdout_line or "timed out" in stdout_line.lower():
                        color_code = "\033[93m"  # 黄色
                        status = " ✗ 超时"
                    else:
                        color_code = "\033[0m"
                        status = ""
                    
                    # 格式化并显示
                    timestamped_line = f"{color_code}[{current_time}] {stdout_line}{status}\033[0m"
                    print(timestamped_line)
                    
                    # 保存到日志
                    if log_file:
                        try:
                            with open(log_file, 'a', encoding=system_encoding) as f:
                                f.write(f"[{current_time}] {stdout_line}\n")
                        except:
                            pass
            except queue.Empty:
                pass
            
            # 处理错误输出
            try:
                while True:
                    stderr_line = stderr_queue.get_nowait()
                    if stderr_line is None:
                        break
                    if stderr_line.startswith("READ_ERROR:"):
                        print(f"\033[91m❌ 读取错误: {stderr_line[12:]}\033[0m")
                        continue
                    
                    current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    timestamped_line = f"\033[91m[{current_time}] ERROR: {stderr_line}\033[0m"
                    print(timestamped_line)
                    
                    if log_file:
                        try:
                            with open(log_file, 'a', encoding=system_encoding) as f:
                                f.write(f"[{current_time}] ERROR: {stderr_line}\n")
                        except:
                            pass
            except queue.Empty:
                pass
            
            # 检查进程是否终止
            if ping_process.poll() is not None:
                print(f"\033[91m\n⚠️ Ping进程意外终止! 返回码: {ping_process.returncode}\033[0m")
                break
            
            # 避免CPU占用过高
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\n" + "="*60)
        print("【监控停止】用户通过 Ctrl+C 停止了监控")
        
        # 尝试终止ping进程
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(ping_process.pid)], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            print(f"终止进程时出错: {str(e)}")
        
        # 记录结束时间
        if log_file:
            try:
                end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(log_file, 'a', encoding=system_encoding) as f:
                    f.write(f"\n===== 停止监控于 {end_time} =====\n\n")
            except:
                pass
        
        print(f"完整日志已保存至: {os.path.abspath(log_file) if log_file else 'N/A'}")
        print("提示：您可以打开日志文件查看完整记录")

if __name__ == "__main__":
    main()
