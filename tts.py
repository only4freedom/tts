# -*- coding: utf-8 -*-
import sys
import os
import re
import asyncio
import subprocess
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, QComboBox, QHBoxLayout, QSlider
from PyQt5.QtCore import pyqtSlot, QThread, pyqtSignal, Qt, QUrl, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import QFont
import edge_tts
import lameenc

OUTPUT_FILE = "output.mp3"
DEFAULT_VOICE = {}   # 👈 初始化为空，后面自动填充
MAX_SEGMENT_LENGTH = 1000


# 🔹 获取微软 Edge TTS 的所有发音人，只保留 中文(大陆/香港/台湾) + 美国英文
async def get_filtered_voices():
    voices = await edge_tts.list_voices()

    filtered = {}
    for v in voices:
        short_name = v["ShortName"]
        locale = v["Locale"]
        gender = v["Gender"]

        # 中文（大陆/香港/台湾）
        if locale.startswith("zh-CN") or locale.startswith("zh-HK") or locale.startswith("zh-TW"):
            display_name = f"{locale} - {short_name} ({gender})"
            filtered[display_name] = short_name

        # 美国英文
        elif locale == "en-US":
            display_name = f"{locale} - {short_name} ({gender})"
            filtered[display_name] = short_name

    return filtered


# ====================== TTS 逻辑 ======================
async def process_segment(segment, voice, rate, volume):
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

        # 👇 使用代理访问 Edge TTS
        communicate = edge_tts.Communicate(
            segment,
            voice,
            rate=rates,
            volume=volumes,
            proxy="http://127.0.0.1:1080"
        )

        segment_audio = b''
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                segment_audio += chunk["data"]
        return segment_audio


async def run_tts(text, voice, rate, volume, finished_callback):
    segments = re.split(r'(\{pause=\d+\})', text)
    combined_audio = b''

    try:
        for segment in segments:
            if re.match(r'\{pause=\d+\}', segment):
                pause_duration = int(re.search(r'\d+', segment).group())
                silence = await asyncio.to_thread(generate_silence, pause_duration)
                combined_audio += silence
            elif segment:
                segment_audio = await process_segment(segment, voice, rate, volume)
                combined_audio += segment_audio

        with open(OUTPUT_FILE, "wb") as f:
            f.write(combined_audio)

    except Exception as e:
        finished_callback(f"出现意外错误：{e}")
        return

    finished_callback("语音生成完毕！")


def generate_silence(duration_ms, sample_rate=24000, bit_depth=16):
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
    finished = pyqtSignal(str)

    def __init__(self, text, voice, rate, volume):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        self.volume = volume

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_tts(self.text, self.voice, self.rate, self.volume, self.finished.emit))


# ====================== 界面部分 ======================
class TTSApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('文字转语音工具')
        self.setGeometry(300, 300, 1000, 800)

        self.last_pause_insertion_position = -1
        self.animation_index = 0
        self.player = QMediaPlayer()

        # 👇 在初始化时加载语音人
        asyncio.run(self.load_voices())

        self.setupUI()

    async def load_voices(self):
        global DEFAULT_VOICE
        DEFAULT_VOICE = await get_filtered_voices()

    def setupUI(self):
        self.layout = QVBoxLayout(self)
        font = QFont('Arial', 14)
        self.setFont(font)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入文字...")
        self.layout.addWidget(self.text_input)

        self.voice_dropdown = QComboBox()
        self.voice_dropdown.addItems(list(DEFAULT_VOICE.keys()))
        self.layout.addWidget(self.voice_dropdown)

        # 语速
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-100, 100)
        self.rate_slider.setValue(0)
        self.rate_label = QLabel('语速增减（0）')
        self.layout.addWidget(self.rate_label)
        self.layout.addWidget(self.rate_slider)
        self.rate_slider.valueChanged.connect(lambda v: self.rate_label.setText(f'语速增减（{v}）'))

        # 音量
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(-100, 100)
        self.volume_slider.setValue(0)
        self.volume_label = QLabel('音调增减（0）')
        self.layout.addWidget(self.volume_label)
        self.layout.addWidget(self.volume_slider)
        self.volume_slider.valueChanged.connect(lambda v: self.volume_label.setText(f'音调增减（{v}）'))

        # 按钮
        button_layout = QHBoxLayout()
        self.layout.addLayout(button_layout)

        self.insert_pause_button = QPushButton('插入停顿')
        self.insert_pause_button.clicked.connect(self.insert_pause)
        button_layout.addWidget(self.insert_pause_button)

        self.generate_button = QPushButton('生成')
        self.generate_button.clicked.connect(self.start_tts)
        button_layout.addWidget(self.generate_button)

        self.play_button = QPushButton('试听')
        self.play_button.clicked.connect(self.toggleAudioPlay)
        button_layout.addWidget(self.play_button)

        self.open_file_button = QPushButton('打开文件位置')
        self.open_file_button.clicked.connect(self.open_file_location)
        button_layout.addWidget(self.open_file_button)

        self.status_label = QLabel('')
        self.layout.addWidget(self.status_label)

        self.slider = QSlider(Qt.Horizontal)
        se
