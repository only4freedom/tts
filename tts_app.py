# -*- coding: utf-8 -*-
import sys
import os
import re
import asyncio
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit,
                              QPushButton, QLabel, QComboBox, QHBoxLayout,
                              QSlider)
from PyQt5.QtCore import pyqtSlot, QThread, pyqtSignal, Qt, QUrl, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import QFont
import edge_tts
import lameenc
from edge_tts import SubMaker  # 导入官方推荐的 SSML 构建工具

# --- 全局设置 ---
OUTPUT_FILE = "output.mp3"
DEFAULT_VOICE = {
    # 中国大陆
    'Xiaoxiao-晓晓 (女)': 'zh-CN-XiaoxiaoNeural',
    'Yunyang-云扬 (男)': 'zh-CN-YunyangNeural',
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

# 晓晓支持的语气风格
XIAOXIAO_STYLES = {
    "默认": None,
    "聊天": "chat",
    "客服": "customerservice",
    "智能助手": "assistant",
    "新闻播报": "newscast",
    "平静": "calm",
    "高兴": "cheerful",
    "深情": "affectionate",
    "温柔": "gentle",
    "抒情": "lyrical",
    "诗歌朗读": "poetry-reading",
    "悲伤": "sad",
    "愤怒": "angry",
    "不满": "disgruntled",
    "害怕": "fearful",
    "严肃": "serious",
}


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


async def process_text_segment(segment, voice, rate, pitch, style=None):
    """
    【最终修正版】使用官方 SubMaker 构建 SSML，确保风格、语速、音调被正确解析。
    """
    rate_str = f"{rate * 5:+d}%"
    pitch_str = f"{pitch * 5:+d}Hz"
    
    # 使用 SubMaker 来安全地构建 SSML
    sub_maker = SubMaker()
    
    # 【修正点】使用 .append() 方法，而不是 .add_sub()
    sub_maker.append(edge_tts.VoiceCommand(voice, rate=rate_str, pitch=pitch_str))
    if style:
        sub_maker.append(edge_tts.StyleCommand(style))
    sub_maker.append(edge_tts.TextCommand(segment))
    
    # 将 SubMaker 对象转换为最终的 SSML 字符串
    final_ssml = sub_maker.to_ssml()
    
    # 在创建 Communicate 对象时传入 SSML 文本
    communicate = edge_tts.Communicate(final_ssml)
    
    segment_audio = b''
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            segment_audio += chunk["data"]
            
    return segment_audio


async def run_tts(text, voice, rate, pitch, style, finished_callback):
    """运行TTS转换"""
    # 按照停顿标记分割文本
    segments = re.split(r'(\{pause=\d+\})', text)
    combined_audio = b''
    
    try:
        for segment in segments:
            if re.match(r'(\{pause=\d+\}', segment):
                # 处理停顿
                pause_duration = int(re.search(r'\d+', segment).group())
                # 使用 to_thread 在异步函数中运行同步的 lameenc 代码
                silence = await asyncio.to_thread(generate_silence, pause_duration)
                combined_audio += silence
            elif segment.strip():  # 只处理非空段落
                # 处理文本段落
                segment_audio = await process_text_segment(segment, voice, rate, pitch, style)
                combined_audio += segment_audio

        # 将合并后的音频写入文件
        with open(OUTPUT_FILE, "wb") as f:
            f.write(combined_audio)

        finished_callback("语音生成完毕！")
        
    except Exception as e:
        finished_callback(f"生成失败：{str(e)}")


class TTSWorker(QThread):
    """TTS工作线程，用于在后台执行异步任务"""
    finished = pyqtSignal(str)

    def __init__(self, text, voice, rate, pitch, style):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.style = style

    def run(self):
        try:
            # 兼容不同平台和环境的 asyncio 事件循环策略
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                run_tts(self.text, self.voice, self.rate, self.pitch, self.style,
                       self.finished.emit)
            )
        except Exception as e:
            self.finished.emit(f"线程错误: {e}")


class TTSApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('文字转语音工具 (纯Python版)')
        self.setGeometry(300, 300, 1000, 850)
        self.last_pause_insertion_position = -1
        self.animation_index = 0
        self.player = QMediaPlayer()
        self.userIsInteracting = False
        
        self.button_style = """
            QPushButton {
                background-color: #4CAF50; border: none; color: white;
                padding: 10px 20px; text-align: center; font-size: 16px;
                margin: 4px 2px; border-radius: 10px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #ccc; color: #666; }
        """
        
        self.setupUI()

    def setupUI(self):
        """设置用户界面"""
        self.layout = QVBoxLayout(self)
        font = QFont('Arial', 14)
        self.setFont(font)
        self.player.error.connect(self.handle_error)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("在这里输入要转换的文字...")
        self.layout.addWidget(self.text_input)

        self.voice_dropdown = QComboBox()
        self.voice_dropdown.addItems(list(DEFAULT_VOICE.keys()))
        self.voice_dropdown.currentTextChanged.connect(self.on_voice_changed)
        self.layout.addWidget(QLabel('选择语音：'))
        self.layout.addWidget(self.voice_dropdown)

        self.style_label = QLabel('选择风格 (仅部分语音支持):')
        self.layout.addWidget(self.style_label)
        self.style_dropdown = QComboBox()
        self.style_dropdown.addItems(list(XIAOXIAO_STYLES.keys()))
        self.layout.addWidget(self.style_dropdown)

        self.rate_label = QLabel('语速增减 (0)')
        self.layout.addWidget(self.rate_label)
        self.rate_slider = QSlider(Qt.Horizontal)
        self.rate_slider.setRange(-10, 10)
        self.rate_slider.setValue(0)
        self.rate_slider.valueChanged.connect(self.update_rate_label)
        self.layout.addWidget(self.rate_slider)

        self.pitch_label = QLabel('音调增减 (0)')
        self.layout.addWidget(self.pitch_label)
        self.pitch_slider = QSlider(Qt.Horizontal)
        self.pitch_slider.setRange(-10, 10)
        self.pitch_slider.setValue(0)
        self.pitch_slider.valueChanged.connect(self.update_pitch_label)
        self.layout.addWidget(self.pitch_slider)

        self.button_layout = QHBoxLayout()
        self.layout.addLayout(self.button_layout)
        
        self.insert_pause_button = QPushButton('插入停顿')
        self.insert_pause_button.setStyleSheet(self.button_style)
        self.insert_pause_button.clicked.connect(self.insert_pause)
        self.button_layout.addWidget(self.insert_pause_button)
        
        self.generate_button = QPushButton('生成语音')
        self.generate_button.setStyleSheet(self.button_style)
        self.generate_button.clicked.connect(self.start_tts)
        self.button_layout.addWidget(self.generate_button)
        
        self.play_button = QPushButton('试听')
        self.play_button.setStyleSheet(self.button_style)
        self.play_button.clicked.connect(self.toggleAudioPlay)
        self.button_layout.addWidget(self.play_button)
        
        self.open_file_button = QPushButton('打开文件位置')
        self.open_file_button.setStyleSheet(self.button_style)
        self.open_file_button.clicked.connect(self.open_file_location)
        self.button_layout.addWidget(self.open_file_button)

        self.status_label = QLabel('')
        self.layout.addWidget(self.status_label)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderPressed.connect(self.slider_pressed)
        self.slider.sliderReleased.connect(self.slider_released)
        self.start_time_label = QLabel("00:00")
        self.end_time_label = QLabel("00:00")
        
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.start_time_label)
        progress_layout.addWidget(self.slider)
        progress_layout.addWidget(self.end_time_label)
        self.layout.addLayout(progress_layout)

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_status_animation)

        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.stateChanged.connect(self.handle_play_state_change)

        self.on_voice_changed(self.voice_dropdown.currentText())

    def on_voice_changed(self, voice_name):
        """当语音选择改变时，控制风格下拉框的启用状态"""
        if voice_name == 'Xiaoxiao-晓晓 (女)':
            self.style_label.setEnabled(True)
            self.style_dropdown.setEnabled(True)
        else:
            self.style_label.setEnabled(False)
            self.style_dropdown.setEnabled(False)
            self.style_dropdown.setCurrentIndex(0)

    def update_rate_label(self, value): self.rate_label.setText(f'语速增减 ({value})')
    def update_pitch_label(self, value): self.pitch_label.setText(f'音调增减 ({value})')
    def handle_error(self): self.status_label.setText("播放器错误:" + self.player.errorString())
    def slider_pressed(self): self.userIsInteracting = True
    def slider_released(self): self.userIsInteracting = False; self.player.setPosition(self.slider.value())
    
    @pyqtSlot(QMediaPlayer.State)
    def handle_play_state_change(self, state):
        self.play_button.setText("停止" if state == QMediaPlayer.PlayingState else "试听")
        self.enableButtons(state != QMediaPlayer.PlayingState)

    @pyqtSlot()
    def toggleAudioPlay(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.stop()
        else:
            file_path = os.path.abspath(OUTPUT_FILE)
            if os.path.exists(file_path):
                self.player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
                self.player.play()
            else:
                self.status_label.setText("请先生成语音文件！")

    def enableButtons(self, enable):
        self.generate_button.setEnabled(enable)
        self.insert_pause_button.setEnabled(enable)
        self.open_file_button.setEnabled(enable)

    def position_changed(self, position):
        if not self.userIsInteracting:
            self.slider.setValue(position)
        self.start_time_label.setText(self.format_time(position))

    def duration_changed(self, duration):
        self.slider.setRange(0, duration)
        self.end_time_label.setText(self.format_time(duration))

    def format_time(self, ms):
        s = ms // 1000
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    @pyqtSlot()
    def start_tts(self):
        """开始TTS转换"""
        text = self.text_input.toPlainText()
        if not text.strip():
            self.status_label.setText("请输入一些文本！")
            return

        selected_voice_name = self.voice_dropdown.currentText()
        voice_id = DEFAULT_VOICE.get(selected_voice_name)
        rate = self.rate_slider.value()
        pitch = self.pitch_slider.value()
        
        style = None
        if self.style_dropdown.isEnabled():
            selected_style = self.style_dropdown.currentText()
            style = XIAOXIAO_STYLES.get(selected_style)

        self.unload_and_remove_old_audio()
        self.enableButtons(False)
        self.play_button.setEnabled(False)

        self.animation_index = 0
        self.animation_timer.start(500)

        self.tts_thread = TTSWorker(text, voice_id, rate, pitch, style)
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
        animation_states = ["正在生成中", "正在生成中.", "正在生成中..", "正在生成中..."]
        self.status_label.setText(animation_states[self.animation_index])
        self.animation_index = (self.animation_index + 1) % len(animation_states)

    @pyqtSlot(str)
    def tts_finished(self, message):
        """TTS完成回调"""
        self.animation_timer.stop()
        self.enableButtons(True)
        self.play_button.setEnabled(True)
        self.status_label.setText(message)
        
        if "完毕" in message and os.path.exists(OUTPUT_FILE):
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(OUTPUT_FILE))))

    @pyqtSlot()
    def insert_pause(self):
        """插入停顿标记，例如 {pause=1000} 代表停顿1秒"""
        self.text_input.insertPlainText("{pause=1000}")

    @pyqtSlot()
    def open_file_location(self):
        """打开文件所在位置"""
        folder_path = os.path.dirname(os.path.abspath(OUTPUT_FILE))
        try:
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':
                os.system(f'open "{folder_path}"')
            else: # linux
                os.system(f'xdg-open "{folder_path}"')
        except Exception as e:
            self.status_label.setText(f"无法打开文件夹：{e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TTSApp()
    ex.show()
    sys.exit(app.exec_())
