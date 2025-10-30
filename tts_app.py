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
from xml.sax.saxutils import escape

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
    'UK-Maisie (女
