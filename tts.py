# -*- coding: utf-8 -*-
import sys
import os
import re
import asyncio
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, QComboBox, QHBoxLayout, QSlider
from PyQt5.QtCore import pyqtSlot, QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import QFont
import pyttsx3
import lameenc
import wave
import struct
import subprocess
from PyQt5.QtCore import QTimer

# === 配置区 ===
OUTPUT_FILE = "output.mp3"
MAX_SEGMENT_LENGTH = 1000  # 设置每个文本段的最大长度

# === 获取本地TTS发音人 ===
engine = pyttsx3.init()
voices = engine.getProperty('voices')
LOCAL_VOICES = {voice.name: voice.id for voice in voices}

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

def tts_to_mp3(text, voice_id, rate=0, volume=1.0):
    """使用 pyttsx3 将文本生成 MP3"""
    tmp_wav = "tmp.wav"
    engine = pyttsx3.init()
    engine.setProperty('voice', voice_id)
    engine.setProperty('rate', 200 + rate)  # 默认200
    engine.setProperty('volume', max(0.0, min(volume, 1.0)))

    # 保存 WAV
    engine.save_to_file(text, tmp_wav)
    engine.runAndWait()
    engine.stop()

    # 转 MP3
    mp3_data = b''
    with wave.open(tmp_wav, 'rb') as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        frames = wf.readframes(nframes)

        encoder = lameenc.Encoder()
        encoder.set_channels(channels)
        encoder.set_in_sample_rate(framerate)
        encoder.set_bit_rate(128)
        encoder.set_out_sample_rate(framerate)
        encoder.set_quality(2)
        mp3_data = encoder.encode(frames)
        mp3_data += encoder.flush()

    os.remove(tmp_wav)
    return mp3_data

async def process_segment(segment, voice, rate, volume):
    if re.match(r'\{pause=\d+\}', segment):
        pause_duration = int(re.search(r'\d+', segment).group())
        silence_bytes = await asyncio.to_thread(generate_silence, pause_duration)
        return silence_bytes
    else:
        segment_audio = await asyncio.to_thread(tts_to_mp3, segment, voice, rate, volume)
        return segment_audio

async def run_tts(text, voice, rate, volume, finished_callback):
    segments = re.split(r'(\{pause=\d+\})', text)
    combined_audio = b''

    try:
        for segment in segments:
            if segment:
                audio = await process_segment(segment, voice, rate, volume)
                combined_audio += audio

        with open(OUTPUT_FILE, "wb") as f:
            f.write(combined_audio)
    except Exception as e:
        finished_callback(f"出现意外错误：{e}")
        return

    finished_callback("语音生成完毕！")

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

class TTSApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('文字转语音工具')
        self.setGeometry(300, 300, 1000, 800)
        self.last_pause_insertion_position = -1
        self.animation_index = 0
        self.player = QMediaPlayer()
        self.setupUI()

    def setupUI(self):
        self.layout = QVBoxLayout(self)

        font = QFont('Arial', 14)
        self.setFont(font)
        self.player.error.connect(self.handle_error)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入文字...")
        self.layout.addWidget(self.text_input)

        self.voice_dropdown = QComboBox()
        self.voice_dropdown.addItems(list(LOCAL_VOICES.keys()))
        self.layout.addWidget(self.voice_dropdown)

        self.button_layout = QHBoxLayout()
        self.layout.addLayout(self.button_layout)

        button_style = """
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 10px 20px;
                text-align: center;
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

        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-100, 100)
        self.rate_slider.setValue(0)
        self.rate_label = QLabel('语速增减（0）')
        self.layout.addWidget(self.rate_label)
        self.layout.addWidget(self.rate_slider)
        self.rate_slider.valueChanged.connect(self.update_rate_label)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_label = QLabel('音量（100%）')
        self.layout.addWidget(self.volume_label)
        self.layout.addWidget(self.volume_slider)
        self.volume_slider.valueChanged.connect(self.update_volume_label)

        self.insert_pause_button = QPushButton('插入停顿')
        self.insert_pause_button.setStyleSheet(button_style)
        self.insert_pause_button.clicked.connect(self.insert_pause)
        self.button_layout.addWidget(self.insert_pause_button)

        self.generate_button = QPushButton('生成')
        self.generate_button.setStyleSheet(button_style)
        self.generate_button.clicked.connect(self.start_tts)
        self.button_layout.addWidget(self.generate_button)

        self.play_button = QPushButton('试听')
        self.play_button.setStyleSheet(button_style)
        self.play_button.clicked.connect(self.toggleAudioPlay)
        self.button_layout.addWidget(self.play_button)

        self.open_file_button = QPushButton('打开文件位置')
        self.open_file_button.setStyleSheet(button_style)
        self.open_file_button.clicked.connect(self.open_file_location)
        self.button_layout.addWidget(self.open_file_button)

        self.status_label = QLabel('')
        self.layout.addWidget(self.status_label)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)
        self.layout.addWidget(self.slider)

        self.userIsInteracting = False
        self.slider.sliderPressed.connect(lambda: setattr(self, 'userIsInteracting', True))
        self.slider.sliderReleased.connect(lambda: setattr(self, 'userIsInteracting', False))

        self.start_time_label = QLabel("00:00")
        self.end_time_label = QLabel("00:00")
        self.progress_layout = QHBoxLayout()
        self.progress_layout.addWidget(self.start_time_label)
        self.progress_layout.addWidget(self.slider)
        self.progress_layout.addWidget(self.end_time_label)
        self.layout.addLayout(self.progress_layout)

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_status_animation)

        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.mediaStatusChanged.connect(self.media_status_changed)
        self.player.stateChanged.connect(self.handle_play_state_change)

    def update_rate_label(self, value):
        self.rate_label.setText(f'语速增减（{value}）')

    def update_volume_label(self, value):
        self.volume_label.setText(f'音量（{self.volume_slider.value()}%）')

    def handle_error(self):
        self.status_label.setText("播放器错误:" + self.player.errorString())

    def slider_pressed(self):
        self.userIsInteracting = True

    def slider_released(self):
        self.userIsInteracting = False
        self.player.setPosition(self.slider.value())

    @pyqtSlot(QMediaPlayer.State)
    def handle_play_state_change(self, state):
        if state == QMediaPlayer.PlayingState:
            self.play_button.setText("停止")
            self.enableButtons(False)
        else:
            self.play_button.setText("试听")
            self.enableButtons(True)

    @pyqtSlot()
    def toggleAudioPlay(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.stop()
        else:
            if self.player.mediaStatus() in [QMediaPlayer.NoMedia, QMediaPlayer.LoadedMedia]:
                self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE))))
            self.player.play()

    def enableButtons(self, enable):
        self.generate_button.setEnabled(enable)
        self.insert_pause_button.setEnabled(enable)
        self.open_file_button.setEnabled(enable)

    def position_changed(self, position):
        self.start_time_label.setText(self.format_time(position))
        if not self.userIsInteracting:
            self.slider.blockSignals(True)
            self.slider.setValue(position)
            self.slider.blockSignals(False)

    def media_status_changed(self, status):
        pass

    def duration_changed(self, duration):
        self.slider.setRange(0, duration)
        self.end_time_label.setText(self.format_time(duration))

    def format_time(self, milliseconds):
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes:02d}:{seconds:02d}"

    @pyqtSlot()
    def start_tts(self):
        text = self.text_input.toPlainText()
        selected_voice_name = self.voice_dropdown.currentText()
        voice_id = LOCAL_VOICES.get(selected_voice_name)
        rate = self.rate_slider.value()
        volume = self.volume_slider.value() / 100.0

        if text.strip() == "":
            self.status_label.setText("请输入一些文本！")
            return

        self.unload_and_remove_old_audio()
        self.generate_button.setDisabled(True)
        self.insert_pause_button.setDisabled(True)
        self.open_file_button.setDisabled(True)
        self.play_button.setDisabled(True)

        self.animation_index = 0
        self.animation_timer.start(500)

        self.tts_thread = TTSWorker(text, voice_id, rate, volume)
        self.tts_thread.finished.connect(self.tts_finished)
        self.tts_thread.start()

    def unload_and_remove_old_audio(self):
        self.player.stop()
        self.player.setMedia(QMediaContent())
        try:
            if os.path.exists(OUTPUT_FILE):
                os.remove(OUTPUT_FILE)
        except Exception as e:
            print(f"删除旧音频文件时出错: {e}")

    def update_status_animation(self):
        animation_states = ["生成中", "生成中.", "生成中..", "生成中..."]
        self.status_label.setText(animation_states[self.animation_index])
        self.animation_index = (self.animation_index + 1) % len(animation_states)

    @pyqtSlot(str)
    def tts_finished(self, message):
        self.animation_timer.stop()
        self.generate_button.setDisabled(False)
        self.insert_pause_button.setDisabled(False)
        self.open_file_button.setDisabled(False)
        self.play_button.setDisabled(False)
        self.status_label.setText("语音文件生成完毕")
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE))))
        self.player.durationChanged.emit(self.player.duration())

    @pyqtSlot()
    def insert_pause(self):
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
        file_path = os.path.abspath(OUTPUT_FILE)
        folder_path = os.path.dirname(file_path)
        self.status_label.setText(folder_path)
        try:
            if sys.platform.startswith('darwin'):
                subprocess.run(['open', folder_path], check=True)
            elif sys.platform.startswith('win32'):
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
