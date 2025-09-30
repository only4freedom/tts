# -*- coding: utf-8 -*-
import sys
import os
import re
import asyncio
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, 
                              QPushButton, QLabel, QComboBox, QHBoxLayout, 
                              QSlider, QLineEdit, QCheckBox)
from PyQt5.QtCore import pyqtSlot, QThread, pyqtSignal, Qt, QUrl, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import QFont
import edge_tts
import subprocess
import lameenc

OUTPUT_FILE = "output.mp3"
DEFAULT_VOICE = {
    # 中国大陆
    'Yunyang-云扬 (男)': 'zh-CN-YunyangNeural',
    'Xiaoxiao-晓晓 (女)': 'zh-CN-XiaoxiaoNeural',
    'Xiaoyi-晓伊 (女)': 'zh-CN-XiaoyiNeural',
    'Yunjian-云健 (男)': 'zh-CN-YunjianNeural',
    'Yunxi-云希 (男)': 'zh-CN-YunxiNeural',
    'Yunxia-云夏 (男)': 'zh-CN-YunxiaNeural',
    'liaoning-Xiaobei-晓北辽宁 (女)': 'zh-CN-liaoning-XiaobeiNeural',
    'shaanxi-Xiaoni-陕西晓妮 (女)': 'zh-CN-shaanxi-XiaoniNeural',
    
    # 中国香港
    'HK-HiuGaai-曉佳 (女)': 'zh-HK-HiuGaaiNeural',
    'HK-HiuMaan-曉曼 (女)': 'zh-HK-HiuMaanNeural',
    'HK-WanLung-雲龍 (男)': 'zh-HK-WanLungNeural',
    
    # 中国台湾
    'TW-HsiaoChen-曉臻 (女)': 'zh-TW-HsiaoChenNeural',
    'TW-YunJhe-雲哲 (男)': 'zh-TW-YunJheNeural',
    'TW-HsiaoYu-曉雨 (女)': 'zh-TW-HsiaoYuNeural',
    
    # 美国英语
    'US-Aria (女)': 'en-US-AriaNeural',
    'US-Ana (女)': 'en-US-AnaNeural',
    'US-Christopher (男)': 'en-US-ChristopherNeural',
    'US-Eric (男)': 'en-US-EricNeural',
    'US-Guy (男)': 'en-US-GuyNeural',
    'US-Jenny (女)': 'en-US-JennyNeural',
    'US-Michelle (女)': 'en-US-MichelleNeural',
    'US-Roger (男)': 'en-US-RogerNeural',
    'US-Steffan (男)': 'en-US-SteffanNeural',
    
    # 英国英语
    'UK-Libby (女)': 'en-GB-LibbyNeural',
    'UK-Maisie (女)': 'en-GB-MaisieNeural',
    'UK-Ryan (男)': 'en-GB-RyanNeural',
    'UK-Sonia (女)': 'en-GB-SoniaNeural',
    'UK-Thomas (男)': 'en-GB-ThomasNeural'
}

MAX_SEGMENT_LENGTH = 1000


async def process_segment(segment, voice, rate, volume, proxy=None):
    """处理单个文本段落或停顿"""
    if re.match(r'\{pause=\d+\}', segment):
        pause_duration = int(re.search(r'\d+', segment).group())
        silence_bytes = await asyncio.to_thread(generate_silence, pause_duration)
        return silence_bytes
    else:
        if rate >= 0:
            rates = "+" + str(rate) + "%"
        else:
            rates = str(rate) + "%"
        if volume >= 0:
            volumes = "+" + str(volume) + "%"
        else:
            volumes = str(volume) + "%"
        
        # 加入代理支持
        communicate = edge_tts.Communicate(segment, voice, rate=rates, volume=volumes, proxy=proxy)
        segment_audio = b''
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                segment_audio += chunk["data"]
        return segment_audio


async def run_tts(text, voice, rate, volume, finished_callback, proxy=None):
    """运行TTS转换"""
    segments = re.split(r'(\{pause=\d+\})', text)
    combined_audio = b''
    
    try:
        for segment in segments:
            if re.match(r'\{pause=\d+\}', segment):
                pause_duration = int(re.search(r'\d+', segment).group())
                silence = await asyncio.to_thread(generate_silence, pause_duration)
                combined_audio += silence
            elif segment.strip():  # 只处理非空段落
                segment_audio = await process_segment(segment, voice, rate, volume, proxy)
                combined_audio += segment_audio

        with open(OUTPUT_FILE, "wb") as f:
            f.write(combined_audio)

        finished_callback("语音生成完毕！")
        
    except Exception as e:
        finished_callback(f"生成失败：{str(e)}")


def generate_silence(duration_ms, sample_rate=24000, bit_depth=16):
    """生成指定时长的静音音频"""
    num_frames = int(sample_rate * duration_ms / 1000)
    silent_frame = b'\x00' * (bit_depth // 8) * num_frames

    encoder = lameenc.Encoder()
    encoder.set_channels(1)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_bit_rate(128)
    encoder.set_out_sample_rate(sample_rate)
    encoder.set_quality(2)

    mp3_data = encoder.encode(silent_frame)
    mp3_data += encoder.flush()

    return mp3_data


class TTSWorker(QThread):
    """TTS工作线程"""
    finished = pyqtSignal(str)

    def __init__(self, text, voice, rate, volume, proxy=None):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.proxy = proxy

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            run_tts(self.text, self.voice, self.rate, self.volume, 
                   self.finished.emit, self.proxy)
        )


class TTSApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('文字转语音工具')
        self.setGeometry(300, 300, 1000, 850)
        self.last_pause_insertion_position = -1
        self.animation_index = 0
        self.player = QMediaPlayer()
        self.userIsInteracting = False
        
        # 定义按钮样式
        self.button_style = """
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 10px 20px;
                text-align: center;
                text-decoration: none;
                font-size: 16px;
                margin: 4px 2px;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """
        
        self.setupUI()

    def setupUI(self):
        """设置用户界面"""
        self.layout = QVBoxLayout(self)

        # 设置整体字体
        font = QFont('Arial', 14)
        self.setFont(font)
        self.player.error.connect(self.handle_error)

        # 文本输入区域
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入文字...")
        self.layout.addWidget(self.text_input)

        # 语音选择下拉框
        self.voice_dropdown = QComboBox()
        self.voice_dropdown.addItems(list(DEFAULT_VOICE.keys()))
        self.layout.addWidget(QLabel('选择语音：'))
        self.layout.addWidget(self.voice_dropdown)

        # 代理设置
        proxy_layout = QHBoxLayout()
        self.proxy_checkbox = QCheckBox('使用代理')
        self.proxy_checkbox.setChecked(True)  # 默认启用
        
        # 代理类型选择
        self.proxy_type_combo = QComboBox()
        self.proxy_type_combo.addItems(['HTTP', 'SOCKS5'])
        self.proxy_type_combo.setMaximumWidth(100)
        
        self.proxy_input = QLineEdit('127.0.0.1:1080')
        self.proxy_input.setPlaceholderText('代理地址（如：127.0.0.1:1080）')
        
        proxy_layout.addWidget(self.proxy_checkbox)
        proxy_layout.addWidget(QLabel('类型:'))
        proxy_layout.addWidget(self.proxy_type_combo)
        proxy_layout.addWidget(QLabel('地址:'))
        proxy_layout.addWidget(self.proxy_input)
        self.layout.addLayout(proxy_layout)

        # 语速滑块
        self.rate_label = QLabel('语速增减（0）')
        self.layout.addWidget(self.rate_label)
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-100, 100)
        self.rate_slider.setValue(0)
        self.rate_slider.valueChanged.connect(self.update_rate_label)
        self.layout.addWidget(self.rate_slider)

        # 音调滑块
        self.volume_label = QLabel('音调增减（0）')
        self.layout.addWidget(self.volume_label)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(-100, 100)
        self.volume_slider.setValue(0)
        self.volume_slider.valueChanged.connect(self.update_volume_label)
        self.layout.addWidget(self.volume_slider)

        # 按钮布局
        self.button_layout = QHBoxLayout()
        self.layout.addLayout(self.button_layout)

        # 插入停顿按钮
        self.insert_pause_button = QPushButton('插入停顿')
        self.insert_pause_button.setStyleSheet(self.button_style)
        self.insert_pause_button.clicked.connect(self.insert_pause)
        self.button_layout.addWidget(self.insert_pause_button)

        # 生成按钮
        self.generate_button = QPushButton('生成')
        self.generate_button.setStyleSheet(self.button_style)
        self.generate_button.clicked.connect(self.start_tts)
        self.button_layout.addWidget(self.generate_button)

        # 试听按钮
        self.play_button = QPushButton('试听')
        self.play_button.setStyleSheet(self.button_style)
        self.play_button.clicked.connect(self.toggleAudioPlay)
        self.button_layout.addWidget(self.play_button)

        # 打开文件位置按钮
        self.open_file_button = QPushButton('打开文件位置')
        self.open_file_button.setStyleSheet(self.button_style)
        self.open_file_button.clicked.connect(self.open_file_location)
        self.button_layout.addWidget(self.open_file_button)

        # 状态标签
        self.status_label = QLabel('')
        self.layout.addWidget(self.status_label)

        # 播放进度条
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)

        # 时间标签
        self.start_time_label = QLabel("00:00")
        self.end_time_label = QLabel("00:00")

        # 进度条布局
        self.progress_layout = QHBoxLayout()
        self.progress_layout.addWidget(self.start_time_label)
        self.progress_layout.addWidget(self.slider)
        self.progress_layout.addWidget(self.end_time_label)
        self.layout.addLayout(self.progress_layout)

        # 初始化定时器
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_status_animation)

        # 连接播放器信号
        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.mediaStatusChanged.connect(self.media_status_changed)
        self.player.stateChanged.connect(self.handle_play_state_change)

    def update_rate_label(self, value):
        """更新语速标签"""
        self.rate_label.setText(f'语速增减（{value}）')

    def update_volume_label(self, value):
        """更新音调标签"""
        self.volume_label.setText(f'音调增减（{value}）')

    def handle_error(self):
        """处理播放器错误"""
        self.status_label.setText("播放器错误:" + self.player.errorString())

    def slider_pressed(self):
        """滑块按下"""
        self.userIsInteracting = True

    def slider_released(self):
        """滑块释放"""
        self.userIsInteracting = False
        self.set_position(self.slider.value())

    def set_position(self, position):
        """设置播放位置"""
        if not self.userIsInteracting:
            self.player.setPosition(position)

    @pyqtSlot(QMediaPlayer.State)
    def handle_play_state_change(self, state):
        """处理播放状态变化"""
        if state == QMediaPlayer.PlayingState:
            self.play_button.setText("停止")
            self.enableButtons(False)
        else:
            self.play_button.setText("试听")
            self.enableButtons(True)

    @pyqtSlot()
    def toggleAudioPlay(self):
        """切换音频播放状态"""
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.stop()
        else:
            if self.player.mediaStatus() in [QMediaPlayer.NoMedia, QMediaPlayer.LoadedMedia]:
                self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE))))
            self.player.play()

    def enableButtons(self, enable):
        """启用或禁用按钮"""
        self.generate_button.setEnabled(enable)
        self.insert_pause_button.setEnabled(enable)
        self.open_file_button.setEnabled(enable)

    def position_changed(self, position):
        """播放位置变化"""
        self.start_time_label.setText(self.format_time(position))
        if not self.userIsInteracting:
            self.slider.blockSignals(True)
            self.slider.setValue(position)
            self.slider.blockSignals(False)

    def media_status_changed(self, status):
        """媒体状态变化"""
        if status == QMediaPlayer.EndOfMedia:
            pass

    def duration_changed(self, duration):
        """时长变化"""
        self.slider.setRange(0, duration)
        self.end_time_label.setText(self.format_time(duration))

    def format_time(self, milliseconds):
        """格式化时间显示"""
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes:02d}:{seconds:02d}"

    @pyqtSlot()
    def start_tts(self):
        """开始TTS转换"""
        text = self.text_input.toPlainText()
        selected_voice_name = self.voice_dropdown.currentText()
        voice_id = DEFAULT_VOICE.get(selected_voice_name)
        rate = self.rate_slider.value()
        volume = self.volume_slider.value()
        
        # 获取代理设置
        proxy = None
        if self.proxy_checkbox.isChecked():
            proxy = self.proxy_input.text().strip()
            if not proxy:
                self.status_label.setText("请输入代理地址或取消勾选代理！")
                return

        if text.strip() == "":
            self.status_label.setText("请输入一些文本！")
            return

        # 卸载并删除旧文件
        self.unload_and_remove_old_audio()

        # 禁用所有按钮
        self.generate_button.setDisabled(True)
        self.insert_pause_button.setDisabled(True)
        self.open_file_button.setDisabled(True)
        self.play_button.setDisabled(True)

        # 开始动画
        self.animation_index = 0
        self.animation_timer.start(500)

        self.tts_thread = TTSWorker(text, voice_id, rate, volume, proxy)
        self.tts_thread.finished.connect(self.tts_finished)
        self.tts_thread.start()

    def unload_and_remove_old_audio(self):
        """卸载并删除旧音频文件"""
        self.player.stop()
        self.player.setMedia(QMediaContent())

        try:
            if os.path.exists(OUTPUT_FILE):
                os.remove(OUTPUT_FILE)
        except Exception as e:
            print(f"删除旧音频文件时出错: {e}")

    def update_status_animation(self):
        """更新状态动画"""
        animation_states = ["生成中", "生成中.", "生成中..", "生成中..."]
        self.status_label.setText(animation_states[self.animation_index])
        self.animation_index = (self.animation_index + 1) % len(animation_states)

    @pyqtSlot(str)
    def tts_finished(self, message):
        """TTS完成回调"""
        self.animation_timer.stop()

        # 启用所有按钮
        self.generate_button.setDisabled(False)
        self.insert_pause_button.setDisabled(False)
        self.open_file_button.setDisabled(False)
        self.play_button.setDisabled(False)
        
        self.status_label.setText(message)
        
        # 如果生成成功，加载音频文件
        if "完毕" in message and os.path.exists(OUTPUT_FILE):
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE))))
            self.player.durationChanged.emit(self.player.duration())

    @pyqtSlot()
    def insert_pause(self):
        """插入停顿标记"""
        pause_text = "{pause=1000}"
        cursor_position = self.text_input.textCursor().position()

        if cursor_position == self.last_pause_insertion_position:
            self.status_label.setText("已经有一个停顿了，不允许插入多个停顿。")
        else:
            self.status_label.clear()

            text_before = self.text_input.toPlainText()[:cursor_position]
            text_after = self.text_input.toPlainText()[cursor_position:]

            if not text_before.endswith(pause_text) and not text_after.startswith(pause_text):
                self.text_input.insertPlainText(pause_text)

            self.last_pause_insertion_position = cursor_position

    @pyqtSlot()
    def open_file_location(self):
        """打开文件所在位置"""
        file_path = os.path.abspath(OUTPUT_FILE)
        folder_path = os.path.dirname(file_path)
        self.status_label.setText(folder_path)
        
        try:
            if sys.platform.startswith('darwin'):  # macOS
                subprocess.run(['open', folder_path], check=True)
            elif sys.platform.startswith('win32'):  # Windows
                os.startfile(folder_path)
            else:
                self.status_label.setText("此操作系统不支持打开文件位置。")
        except Exception as e:
            self.status_label.setText("无法打开文件位置：" + str(e))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TTSApp()
    ex.show()
    sys.exit(app.exec_())
