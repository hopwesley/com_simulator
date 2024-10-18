import time
import os
from email.policy import default

import serial
import threading
from datetime import datetime
import wx  # 引入wxPython
import schedule
from typing import Optional
import serial.tools.list_ports
import glob

path = "D:/NOTC/send"
num_threads = 100  # 定义任务数量
threads = []
data_list = []
wake_events = []
stop_event = threading.Event()
is_running = False
os.makedirs(path, exist_ok=True)  # 确保目录存在
defaultComPort = "/dev/ttys005"  # COM2

serialDelegate: Optional[serial.Serial] = None
job_lock = threading.Lock()


def list_available_ports():
    ports = serial.tools.list_ports.comports()
    available_ports = []
    for port in ports:
        available_ports.append(port.device)
    return available_ports


def list_virtual_ports():
    # 查找所有的虚拟串口设备
    virtual_ports = glob.glob('/dev/ttys*') + glob.glob('/dev/pts/*')
    return virtual_ports


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


def worker(thread_id, local_wake_event):
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

        if serialDelegate.is_open:
            try:
                serialDelegate.write(data.encode('utf-8'))  # 发送数据
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

    serialDelegate.flush()

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


def initialize_serial_delegate():
    global serialDelegate, defaultComPort  # 引用全局的 serialDelegate
    if serialDelegate is None:
        try:
            serialDelegate = serial.Serial(port=defaultComPort, baudrate=19200, timeout=5)
            # 清空串口缓冲区
            serialDelegate.reset_input_buffer()
            serialDelegate.reset_output_buffer()
            print("------>>>串口初始化成功")
        except serial.SerialException as e:
            print(f"---->>>>串口初始化失败: {e}")
            return False  # 如果初始化失败，返回 False
    return True


class MyFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(MyFrame, self).__init__(*args, **kw)
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # 创建自定义的数字输入控件
        self.numeric_control = NumericControl(panel, value=5, min_value=1, max_value=100)

        self.start_button = wx.Button(panel, label="开始")
        self.start_button.Bind(wx.EVT_BUTTON, self.on_start_click)

        # 创建下拉选择框
        self.port_selector = wx.ComboBox(panel, style=wx.CB_READONLY)
        self.populate_ports()  # 初始化下拉框内容
        self.port_selector.Bind(wx.EVT_COMBOBOX, self.on_port_selected)  # 绑定事件

        # 创建动态文本显示区域（滚动）
        self.log_display = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(600, 300))

        sizer.Add(self.numeric_control, 0, wx.ALL | wx.CENTER, 5)
        sizer.Add(self.port_selector, 0, wx.ALL | wx.CENTER, 5)
        sizer.Add(self.start_button, 0, wx.ALL | wx.CENTER, 5)
        sizer.Add(self.log_display, 1, wx.EXPAND | wx.ALL, 5)  # 添加滚动文本区域
        panel.SetSizer(sizer)

        self.SetSize((960, 640))
        self.SetTitle("调度任务控制")

        # schedule.every(20).seconds.do(scheduled_job)
        schedule.every(1).minutes.do(scheduled_job)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, on_timer, self.timer)

        available_ports = list_available_ports()
        print("可用的串口：", available_ports)

        available_virtual_ports = list_virtual_ports()
        print("虚拟串口：", available_virtual_ports)
        self.non_selectable_items = ["物理串口:", "-------------------", "虚拟串口:"]


    def log_message(self, message):
        """向日志显示区域追加消息"""
        self.log_display.AppendText(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
        self.log_display.SetInsertionPointEnd()  # 滚动到文本末尾

    def populate_ports(self):
        """填充物理串口和虚拟串口到下拉框，并添加分割线"""
        available_ports = list_available_ports()
        available_virtual_ports = list_virtual_ports()

        # 添加物理串口
        self.port_selector.Append("物理串口:")
        self.port_selector.Append("-------------------")
        for port in available_ports:
            self.port_selector.Append(port)

        # 添加分割线
        self.port_selector.Append("虚拟串口:")
        self.port_selector.Append("-------------------")
        # 添加虚拟串口
        for vport in available_virtual_ports:
            self.port_selector.Append(vport)

    def on_port_selected(self, event):
        """当用户选择某个串口时，打印出选中的串口"""
        selected_port = self.port_selector.GetValue()

        # 防止用户选择不可选项
        if selected_port in self.non_selectable_items:
            wx.MessageBox("无法选择该项，请选择具体的串口！", "错误", wx.OK | wx.ICON_ERROR)
            self.port_selector.SetValue("")  # 重置选择框的值
        else:
            print(f"选中的串口: {selected_port}")
            self.log_message(f"选中的串口: {selected_port}")

    def on_start_click(self, event):
        global is_running, num_threads
        busy = show_busy_info("正在处理，请稍候...")

        num_threads = self.numeric_control.GetValue()
        print(f"------>>>当前线程数: {num_threads}")
        self.log_message(f"启动任务，线程数: {num_threads}")

        if not is_running:
            self.start_scheduled_tasks()
            self.start_button.SetLabel("停止")
            self.port_selector.Disable()
            is_running = True

        else:
            self.stop_scheduled_tasks()
            self.start_button.SetLabel("开始")
            self.port_selector.Enable()  # 启用下拉框
            is_running = False

        busy = None  # 隐藏等待框

    def start_scheduled_tasks(self):
        global serialDelegate
        if not initialize_serial_delegate():
            self.log_message("串口初始化失败")
            return  # 如果初始化失败，直接返回，不执行任务

        for i in range(num_threads):
            event = threading.Event()
            wake_events.append(event)
            t = threading.Thread(target=worker, args=(i + 1, event))
            threads.append(t)
            t.start()

        self.log_message("所有线程已启动")
        scheduled_job()
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

        self.log_message("所有任务已停止")
        print("------>>>所有任务已停止。")
        stop_event.clear()  # 重置停止事件，准备下一次启动
        self.timer.Stop()  # 停止定时器


class MyApp(wx.App):
    def OnInit(self):
        frame = MyFrame(None)
        frame.Show(True)
        return True


class NumericControl(wx.Panel):
    def __init__(self, parent, value=5, min_value=1, max_value=100):
        super(NumericControl, self).__init__(parent)
        self.min_value = min_value
        self.max_value = max_value

        # 布局管理
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        # 增加文本提示 "模拟信道数："
        self.label = wx.StaticText(self, label="模拟信道数：")

        # 减少按钮
        self.dec_button = wx.Button(self, label="-")
        self.dec_button.Bind(wx.EVT_BUTTON, self.on_decrease)

        # 增加按钮
        self.inc_button = wx.Button(self, label="+")
        self.inc_button.Bind(wx.EVT_BUTTON, self.on_increase)

        # 输入框
        self.text_ctrl = wx.TextCtrl(self, value=str(value), style=wx.TE_CENTER)
        self.text_ctrl.SetMinSize(wx.Size(50, -1))  # 设置宽度为 50
        self.text_ctrl.Bind(wx.EVT_TEXT, self.on_text_change)

        # 添加控件到布局
        hbox.Add(self.label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)  # 添加文本提示
        hbox.Add(self.dec_button, 0, wx.EXPAND | wx.ALL, 5)
        hbox.Add(self.text_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        hbox.Add(self.inc_button, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(hbox)

    def on_decrease(self, event):
        """减少按钮的点击事件"""
        value = int(self.text_ctrl.GetValue())
        if value > self.min_value:
            value -= 1
            self.text_ctrl.SetValue(str(value))

    def on_increase(self, event):
        """增加按钮的点击事件"""
        value = int(self.text_ctrl.GetValue())
        if value < self.max_value:
            value += 1
            self.text_ctrl.SetValue(str(value))

    def on_text_change(self, event):
        """防止用户手动输入超过范围的值"""
        try:
            value = int(self.text_ctrl.GetValue())
        except ValueError:
            self.text_ctrl.SetValue(str(self.min_value))
            return

        if value < self.min_value:
            self.text_ctrl.SetValue(str(self.min_value))
        elif value > self.max_value:
            self.text_ctrl.SetValue(str(self.max_value))

    def GetValue(self):
        """获取当前的值"""
        return int(self.text_ctrl.GetValue())

    def SetValue(self, value):
        """设置当前的值"""
        if self.min_value <= value <= self.max_value:
            self.text_ctrl.SetValue(str(value))


if __name__ == "__main__":
    app = MyApp(False)
    app.MainLoop()
