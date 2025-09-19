# -*- coding: utf-8 -*-
import sys
import os
import re
import asyncio
import threading
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel, QComboBox, QHBoxLayout, QSlider
from PyQt5.QtCore import pyqtSlot, QThread, pyqtSignal, Qt, QUrl, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import QFont
import edge_tts
import subprocess
import lameenc

# === 配置区 ===
OUTPUT_FILE = "output.mp3"
PROXY = None  # 如果有代理，改成 "http://127.0.0.1:1080"

MAX_SEGMENT_LENGTH = 1000

# ========== 自动获取发音人 ==========
async def get_voices():
    all_voices = await edge_tts.list_voices()
    filtered = {}
    for v in all_voices:
        if any(loc in v["locale"] for loc in ["zh-CN", "zh-HK", "zh-TW", "en-US"]):
            name = f"{v['ShortName']}-{v['Name']}"
            filtered[name] = v["ShortName"]
    return filtered

# ========== TTS 核心函数 ==========
async def process_segment(segment, voice, rate, volume):
    if re.match(r'\{pause=\d+\}', segment):
        pause_duration = int(re.search(r'\d+', segment).group())
        silence_bytes = await asyncio.to_thread(generate_silence, pause_duration)
        return silence_bytes
    else:
        rates = f"+{rate}%" if rate >=0 else f"{rate}%"
        volumes = f"+{volume}%" if volume >=0 else f"{volume}%"
        communicate = edge_tts.Communicate(segment, voice, rate=rates, volume=volumes, proxy=PROXY)
        audio = b''
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return audio

async def run_tts(text, voice, rate, volume, finished_callback):
    segments = re.split(r'(\{pause=\d+\})', text)
    combined_audio = b''
    try:
        for segment in segments:
            if re.match(r'\{pause=\d+\}', segment):
                pause_duration = int(re.search(r'\d+', segment).group())
                combined_audio += await asyncio.to_thread(generate_silence, pause_duration)
            elif segment:
                combined_audio += await process_segment(segment, voice, rate, volume)
        with open(OUTPUT_FILE, "wb") as f:
            f.write(combined_audio)
    except Exception as e:
        finished_callback(f"TTS出错: {e}")
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

# ========== PyQt TTSWorker ==========
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

# ========== PyQt GUI ==========
class TTSApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('文字转语音工具')
        self.setGeometry(300, 300, 1000, 800)
        self.last_pause_insertion_position = -1
        self.animation_index = 0
        self.player = QMediaPlayer()
        self.DEFAULT_VOICE = {}
        self.setupUI()
        threading.Thread(target=self.load_voices_thread).start()  # 自动获取发音人

    def load_voices_thread(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        voices = asyncio.run(get_voices())
        self.DEFAULT_VOICE = voices
        self.voice_dropdown.clear()
        self.voice_dropdown.addItems(list(voices.keys()))

    def setupUI(self):
        self.layout = QVBoxLayout(self)
        font = QFont('Arial', 14)
        self.setFont(font)
        self.player.error.connect(self.handle_error)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请输入文字...")
        self.layout.addWidget(self.text_input)

        self.voice_dropdown = QComboBox()
        self.layout.addWidget(self.voice_dropdown)

        self.button_layout = QHBoxLayout()
        self.layout.addLayout(self.button_layout)

        button_style = """
            QPushButton {background-color:#4CAF50;border:none;color:white;padding:10px 20px;text-align:center;font-size:16px;margin:4px 2px;border-radius:10px;}
            QPushButton:hover{background-color:#45a049;}
            QPushButton:disabled{background-color:#ccc;color:#666;}
        """

        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-100,100); self.rate_slider.setValue(0)
        self.rate_label = QLabel('语速增减（0）')
        self.layout.addWidget(self.rate_label)
        self.layout.addWidget(self.rate_slider)
        self.rate_slider.valueChanged.connect(lambda v:self.rate_label.setText(f'语速增减（{v}）'))

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(-100,100); self.volume_slider.setValue(0)
        self.volume_label = QLabel('音调增减（0）')
        self.layout.addWidget(self.volume_label)
        self.layout.addWidget(self.volume_slider)
        self.volume_slider.valueChanged.connect(lambda v:self.volume_label.setText(f'音调增减（{v}）'))

        self.insert_pause_button = QPushButton('插入停顿'); self.insert_pause_button.setStyleSheet(button_style); self.insert_pause_button.clicked.connect(self.insert_pause)
        self.generate_button = QPushButton('生成'); self.generate_button.setStyleSheet(button_style); self.generate_button.clicked.connect(self.start_tts)
        self.play_button = QPushButton('试听'); self.play_button.setStyleSheet(button_style); self.play_button.clicked.connect(self.toggleAudioPlay)
        self.open_file_button = QPushButton('打开文件位置'); self.open_file_button.setStyleSheet(button_style); self.open_file_button.clicked.connect(self.open_file_location)
        for btn in [self.insert_pause_button,self.generate_button,self.play_button,self.open_file_button]: self.button_layout.addWidget(btn)

        self.status_label = QLabel(''); self.layout.addWidget(self.status_label)
        self.slider = QSlider(Qt.Horizontal); self.layout.addWidget(self.slider)
        self.userIsInteracting = False
        self.slider.sliderPressed.connect(lambda: setattr(self,'userIsInteracting',True))
        self.slider.sliderReleased.connect(lambda: setattr(self,'userIsInteracting',False))
        self.start_time_label = QLabel("00:00"); self.end_time_label = QLabel("00:00")
        self.progress_layout = QHBoxLayout(); self.progress_layout.addWidget(self.start_time_label); self.progress_layout.addWidget(self.slider); self.progress_layout.addWidget(self.end_time_label); self.layout.addLayout(self.progress_layout)
        self.animation_timer = QTimer(self); self.animation_timer.timeout.connect(self.update_status_animation)
        self.player.durationChanged.connect(self.duration_changed); self.player.positionChanged.connect(self.position_changed)
        self.player.mediaStatusChanged.connect(self.media_status_changed); self.player.stateChanged.connect(self.handle_play_state_change)

    # ========== PyQt 其他方法 ==========
    def handle_error(self): self.status_label.setText("播放器错误:"+self.player.errorString())
    def toggleAudioPlay(self):
        if self.player.state() == QMediaPlayer.PlayingState: self.player.stop()
        else:
            if self.player.mediaStatus() in [QMediaPlayer.NoMedia,QMediaPlayer.LoadedMedia]:
                self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE))))
            self.player.play()
    def enableButtons(self, enable): self.generate_button.setEnabled(enable); self.insert_pause_button.setEnabled(enable); self.open_file_button.setEnabled(enable)
    def position_changed(self, pos): self.start_time_label.setText(self.format_time(pos)); 
        if not self.userIsInteracting: self.slider.blockSignals(True); self.slider.setValue(pos); self.slider.blockSignals(False)
    def media_status_changed(self, status): pass
    def duration_changed(self, dur): self.slider.setRange(0,dur); self.end_time_label.setText(self.format_time(dur))
    def format_time(self, ms): seconds=ms//1000; minutes=seconds//60; seconds%=60; return f"{minutes:02d}:{seconds:02d}"
    def insert_pause(self):
        pause_text="{pause=1000}"; cur_pos=self.text_input.textCursor().position()
        if cur_pos==self.last_pause_insertion_position: self.status_label.setText("已经有一个停顿了")
        else:
            self.status_label.clear(); text_before=self.text_input.toPlainText()[:cur_pos]; text_after=self.text_input.toPlainText()[cur_pos:]
            if not text_before.endswith(pause_text) and not text_after.startswith(pause_text): self.text_input.insertPlainText(pause_text)
            self.last_pause_insertion_position=cur_pos
    def open_file_location(self):
        folder_path=os.path.dirname(os.path.abspath(OUTPUT_FILE)); self.status_label.setText(folder_path)
        try:
            if sys.platform.startswith('win32'): os.startfile(folder_path)
            elif sys.platform.startswith('darwin'): subprocess.run(['open', folder_path],check=True)
            else: self.status_label.setText("此操作系统不支持打开文件位置")
        except Exception as e: self.status_label.setText("无法打开文件位置："+str(e))
    def start_tts(self):
        text=self.text_input.toPlainText(); selected=self.voice_dropdown.currentText(); voice_id=self.DEFAULT_VOICE.get(selected)
        rate=self.rate_slider.value(); volume=self.volume_slider.value()
        if not text.strip(): self.status_label.setText("请输入文本"); return
        self.player.stop(); self.player.setMedia(QMediaContent()); 
        for btn in [self.generate_button,self.insert_pause_button,self.open_file_button,self.play_button]: btn.setDisabled(True)
        self.animation_index=0; self.animation_timer.start(500)
        self.tts_thread=TTSWorker(text,voice_id,rate,volume); self.tts_thread.finished.connect(self.tts_finished); self.tts_thread.start()
    def update_status_animation(self): anim=["生成中","生成中.","生成中..","生成中..."]; self.status_label.setText(anim[self.animation_index]); self.animation_index=(self.animation_index+1)%4
    @pyqtSlot(str)
    def tts_finished(self,msg):
        self.animation_timer.stop(); 
        for btn in [self.generate_button,self.insert_pause_button,self.open_file_button,self.play_button]: btn.setDisabled(False)
        self.status_label.setText("语音文件生成完毕"); self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE)))); self.player.durationChanged.emit(self.player.duration())

if __name__=='__main__':
    app=QApplication(sys.argv)
    ex=TTSApp()
    ex.show()
    sys.exit(app.exec_())
