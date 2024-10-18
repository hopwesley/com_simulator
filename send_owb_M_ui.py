import time
import os
import serial
import threading
from datetime import datetime
import wx  # 引入wxPython
import schedule

path = "D:/NOTC/send"
num_threads = 100  # 定义任务数量
threads = []
data_list = []
wake_events = []
stop_event = threading.Event()
is_running = False
os.makedirs(path, exist_ok=True)  # 确保目录存在

# 配置串口参数
# ser = serial.Serial(port='COM2', baudrate=19200, timeout=5)
ser = serial.Serial(port='/dev/ttys007', baudrate=19200, timeout=5)
# 清空读缓冲区
ser.reset_input_buffer()
ser.reset_output_buffer()
job_lock = threading.Lock()


def log_file(file_name, log_str):
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
    now = datetime.now()
    current_time_str = now.strftime("%Y%m%d%H%M")[2:]
    for i in range(num_threads):
        data = str1 + current_time_str + str2 + str(hex(i + 1))[2:].zfill(2) + str3
        data = "$" + data + "*" + create_validate(data) + "\r\n"
        data_list.append(data)


def worker(thread_id,local_wake_event):
    thread_name = f"Thread-{thread_id}"
    while not stop_event.is_set():  # 直接使用全局的 stop_event
        # 等待主线程的唤醒事件
        local_wake_event.wait()  # 直接使用全局的 wake_event
        local_wake_event.clear()
        print(f"------>>> worker {thread_name} start")

        if stop_event.is_set():
            print(f"------>>> worker {thread_name} quit")
            return  # 如果停止事件已经设置，直接退出

        data = data_list[thread_id]
        if data == '0':
            print(f"------>>> worker {thread_name} should not has empty data")
            continue

        if ser.is_open:
            try:
                ser.write(data.encode('utf-8'))  # 发送数据
                ser.flush()
                log_file(thread_name, f"发送[{thread_name}] : {data}")
                data_list[thread_id] = '0'
            except serial.SerialTimeoutException as e:
                log_file(thread_name, f"[{thread_name}]写入超时错误: {e}")
            except Exception as e:
                log_file(thread_name, f"[{thread_name}] 错误: {e}")
        else:
            print(f"------>>> worker {thread_name} exit: 串口未打开")
            return  # 如果串口未打开，退出线程

def scheduled_job():
    print("------>>> schedule work start")
    if not job_lock.acquire(blocking=False):
        print("------>>> 任务正在执行，跳过此次触发")
        return

    ser.flush()

    create_data()
    for wake_event in wake_events:
        wake_event.set()

    job_lock.release()


def on_timer(event):
    schedule.run_pending()


def show_busy_info(message):
    busy = wx.BusyInfo(message)
    wx.Yield()  # 确保等待框能及时显示出来
    return busy


class MyFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(MyFrame, self).__init__(*args, **kw)
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # 创建开始按钮
        self.start_button = wx.Button(panel, label="开始")
        self.start_button.Bind(wx.EVT_BUTTON, self.on_start_click)

        sizer.Add(self.start_button, 0, wx.ALL | wx.CENTER, 5)
        panel.SetSizer(sizer)

        self.SetSize((600, 400))
        self.SetTitle("调度任务控制")

        schedule.every(20).seconds.do(scheduled_job)
        # schedule.every(1).minutes.do(scheduled_job)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, on_timer, self.timer)

    def on_start_click(self, event):
        global is_running
        busy = show_busy_info("正在处理，请稍候...")

        if not is_running:
            self.start_scheduled_tasks()
            self.start_button.SetLabel("停止")
            is_running = True

        else:
            self.stop_scheduled_tasks()
            self.start_button.SetLabel("开始")
            is_running = False

        busy = None  # 隐藏等待框

    def start_scheduled_tasks(self):
        create_data()
        for i in range(num_threads):
            event = threading.Event()
            wake_events.append(event)
            event.set()
            t = threading.Thread(target=worker, args=(i + 1,event))
            threads.append(t)
            t.start()

        self.timer.Start(1000)  # 每1秒检查一次任务调度

    def stop_scheduled_tasks(self):
        stop_event.set()  # 触发事件，通知所有线程停止
        for wake_event in wake_events:
            wake_event.set()

        wake_events.clear()

        for t in threads:
            t.join(timeout=2)  # 使用超时，防止无限期阻塞
            if t.is_alive():
                print(f"线程 {t.name} 未能及时退出")

        threads.clear()

        print("------>>>所有任务已停止。")
        stop_event.clear()  # 重置停止事件，准备下一次启动
        self.timer.Stop()  # 停止定时器


class MyApp(wx.App):
    def OnInit(self):
        frame = MyFrame(None)
        frame.Show(True)
        return True


if __name__ == "__main__":
    app = MyApp(False)
    app.MainLoop()
