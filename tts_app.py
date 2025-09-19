# -*- coding: utf-8 -*-
import sys
import os
import pyttsx3
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit,
                             QPushButton, QLabel, QComboBox, QHBoxLayout, QSlider)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl
import subprocess
import time
import wave
import lameenc

OUTPUT_FILE = "output.mp3"
MAX_SEGMENT_LENGTH = 1000  # 每段文本最大长度

class TTSApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('文字转语音工具（本地SAPI5）')
        self.setGeometry(300, 300, 1000, 700)
        self.player = QMediaPlayer()
        self.engine = pyttsx3.init()
        self.setupUI()

    def setupUI(self):
        layout = QVBoxLayout(self)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入文本...")
        layout.addWidget(self.text_input)

        self.voice_dropdown = QComboBox()
        self.voices = self.engine.getProperty('voices')
        self.voice_map = {}
        for v in self.voices:
            name = f"{v.name} ({v.id})"
            self.voice_dropdown.addItem(name)
            self.voice_map[name] = v.id
        layout.addWidget(self.voice_dropdown)

        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(50, 300)
        self.rate_slider.setValue(200)
        layout.addWidget(QLabel("语速"))
        layout.addWidget(self.rate_slider)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        layout.addWidget(QLabel("音量"))
        layout.addWidget(self.volume_slider)

        btn_layout = QHBoxLayout()

        self.generate_btn = QPushButton("生成 MP3")
        self.generate_btn.clicked.connect(self.generate_tts)
        btn_layout.addWidget(self.generate_btn)

        self.play_btn = QPushButton("播放")
        self.play_btn.clicked.connect(self.toggle_play)
        btn_layout.addWidget(self.play_btn)

        self.open_btn = QPushButton("打开文件位置")
        self.open_btn.clicked.connect(self.open_file_location)
        btn_layout.addWidget(self.open_btn)

        layout.addLayout(btn_layout)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def generate_tts(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            self.status_label.setText("请输入文本！")
            return

        self.status_label.setText("生成中...")

        voice_id = self.voice_map[self.voice_dropdown.currentText()]
        rate = self.rate_slider.value()
        volume = self.volume_slider.value() / 100.0

        # pyttsx3生成wav
        temp_wav = "temp.wav"
        self.engine.setProperty('voice', voice_id)
        self.engine.setProperty('rate', rate)
        self.engine.setProperty('volume', volume)
        self.engine.save_to_file(text, temp_wav)
        self.engine.runAndWait()

        # 转mp3
        with wave.open(temp_wav, 'rb') as wf:
            encoder = lameenc.Encoder()
            encoder.set_bit_rate(128)
            encoder.set_in_sample_rate(wf.getframerate())
            encoder.set_channels(wf.getnchannels())
            encoder.set_quality(2)
            pcm_data = wf.readframes(wf.getnframes())
            mp3_data = encoder.encode(pcm_data)
            mp3_data += encoder.flush()
            with open(OUTPUT_FILE, 'wb') as f:
                f.write(mp3_data)

        os.remove(temp_wav)
        self.status_label.setText(f"生成完成：{OUTPUT_FILE}")

        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE))))

    def toggle_play(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.stop()
        else:
            if self.player.mediaStatus() in [QMediaPlayer.NoMedia, QMediaPlayer.LoadedMedia]:
                self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE))))
            self.player.play()

    def open_file_location(self):
        folder = os.path.abspath(".")
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform.startswith("darwin"):
                subprocess.run(["open", folder])
            else:
                self.status_label.setText("此操作系统不支持打开文件位置")
        except Exception as e:
            self.status_label.setText(f"无法打开文件夹: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = TTSApp()
    win.show()
    sys.exit(app.exec_())
