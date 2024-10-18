#---
#北斗3代

import time
import os
import serial
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

path = "D:/NOTC/send"
# message1 = "$BDICP,4216930,0,0,3,0,N,2,N,1,0,0,3,1,60,2,0,0,1,1,21,0,0,0*4E"
num_threads = 100 # 定义任务数量
schedule_key = '0/5'
threads = []
data_list = []
wake_event = threading.Event()
stop_event = threading.Event()

os.makedirs(path, exist_ok=True)  # 确保目录存在

# 配置串口参数
# ser = serial.Serial(port='COM2', baudrate=19200, timeout=5)
ser = serial.Serial(port='/dev/ttys004', baudrate=19200, timeout=5)
# 清空读缓冲区
ser.reset_input_buffer()
# 清空写缓冲区
ser.reset_output_buffer()

def log_file(file_name,log_str):
    ct = datetime.now()
    file_path = os.path.join(path, f"{file_name}.txt")
    try:
        with open(file_path, 'a+', encoding='utf-8') as logfileH:
            logfileH.write(f"[{ct}] {log_str.strip(' \r\n\t')}\n")
        print(f"[{ct}] {log_str.strip(' \r\n\t')}")
    except Exception as e:
        print(f"日志记录失败: {e}")

# 生成校验和
def create_validate(data):
    data_sum = 0
    for i in range(0, len(data)):
        data_sum ^= ord(data[i])
    return str(hex(data_sum))[2:].zfill(2).upper()

# 生成数据
def create_data():
    str1 = "BDTCI,4216930,4216931,2,090359,2,0,244F57425378"
    str2 = "05F8C811DF6FFFFFFFFFFFFFFFFF021F001132000B2100068800029F073A0004FF2E03800355FFFFFFFFFFFFFFFF0004FF2E04BD03550331FFFF018F0BF7001E00"
    str3 = "E0"
    data_list.clear()
    data_list.append('0')
    # 获取当前时间并格式化
    now = datetime.now()
    current_time_str = now.strftime("%Y%m%d%H%M")[2:]
    for i in range(num_threads):
        data = str1 + current_time_str + str2 + str(hex(i + 1))[2:].zfill(2) + str3
        data = "$" + data + "*" + create_validate(data) + "\r\n"
        data_list.append(data)

def worker(thread_id, wake_event, stop_event):
    """
    线程执行的函数。
    参数：
    - thread_id: 线程编号
    - wake_event: 用于唤醒线程的事件
    - stop_event: 用于停止线程的事件
    """
    thread_name = f"Thread-{thread_id}"
    while not stop_event.is_set():
        # 等待主线程的唤醒事件
        wake_event.wait()
        data = data_list[thread_id]
        if data == '0':
            continue
        if stop_event.is_set():
            break  # 检查是否需要停止线程
        # 执行任务
        #print(f"{datetime.now()} - 工作线程 {thread_name} 被唤醒，开始执行任务。")
        #print(f"{datetime.now()} - 工作线程 {thread_name} ser.is_open - {ser.is_open}。")
        # 这里可以添加实际的任务代码
        if ser.is_open:
            try:
                ser.write(data.encode('utf-8'))  # 发送数据
                ser.flush()
                log_file(thread_name,f"发送 : {data}")
                data_list[thread_id] = '0'
            except serial.SerialTimeoutException as e:
                log_file(thread_name, f"[{thread_name}]写入超时错误: {e}")
            except Exception as e:
                log_file(thread_name, f"[{thread_name}] 错误: {e}")

        #print(f"{datetime.now()} - 工作线程 {thread_name} 完成任务，进入休眠。")


def scheduled_job():
    try:
        #print(f"{datetime.now()} - 调度线程：唤醒所有工作线程。")
        create_data()
        wake_event.set()
        all_done = 1
        i = 0
        # 等待所有线程完成任务

        while all_done:
            #print(f"data_list - {data_list}")
            if all(element == data_list[0] for element in data_list) or i == 3:
            # 等待下一次唤醒，将事件状态重置以继续等待
                wake_event.clear()
                all_done = 0
                ser.reset_output_buffer()
                break
            else :
                i = i + 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("调度线程：接收到停止指令，正在停止所有线程。")
        stop_event.set()
        wake_event.set()  # 确保所有线程不再等待
        # 等待所有线程结束
        for t in threads:
            t.join()
        print("调度线程：所有线程已停止。")
    print(f"{datetime.now()} - 调度线程：本次调度完成。")


def main():

    # 创建并启动线程
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i + 1, wake_event, stop_event))
        threads.append(t)
        t.start()

     # 创建后台调度器
    scheduler = BackgroundScheduler()

    # 添加定时任务
    scheduler.add_job(
        scheduled_job,
        trigger='cron',
        minute='*/1',
        second='0',
    )

    # 启动调度器
    scheduler.start()
    print("调度线程：启动完成.")

    while True:

        time.sleep(10)


if __name__ == "__main__":
    main()
