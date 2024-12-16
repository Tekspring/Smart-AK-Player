import sys
import ffmpeg
from PySide2.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QSlider, QWidget, QPushButton, QStyle, QFileDialog
from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QPixmap, QImage
from ffpyplayer.player import MediaPlayer

class CustomSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._is_slider_pressed = False  # 用來跟蹤滑塊是否被按下過

    def mousePressEvent(self, event):
        """捕捉滑軌的點擊事件，避免重複觸發"""
        if event.button() == Qt.LeftButton:
            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                event.pos().x(),
                self.width(),
                upsideDown=False,
            )
            self.setValue(value)  # 更新滑塊到新位置

            # 如果滑塊沒有被按下過，觸發 sliderPressed
            if not self._is_slider_pressed:
                self._is_slider_pressed = True
                self.sliderPressed.emit()  # 觸發 sliderPressed 事件

        super().mousePressEvent(event)  # 保留原始行為

    def mouseReleaseEvent(self, event):
        """捕捉滑塊釋放事件"""
        if event.button() == Qt.LeftButton:
            self._is_slider_pressed = False  # 滑塊釋放後標誌設為 False
            self.sliderReleased.emit()  # 觸發 sliderReleased 事件
        super().mouseReleaseEvent(event)

class VideoPlayer(QMainWindow):
    def __init__(self, video_path):
        super().__init__()
        self.setWindowTitle("Smart Player")
        self.video_path = video_path

        # 播放狀態
        self.is_paused = False  # 是否暫停
        self.slider_pressed = False  # 是否正在拖動滑桿

        # 界面組件
        self.video_label = QLabel("正在加載視頻...")
        self.video_label.setAlignment(Qt.AlignCenter)
        #self.slider = QSlider(Qt.Horizontal)
        self.slider = CustomSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(0)
        self.volume_slider = QSlider(Qt.Horizontal, self)
        self.playback_info = QLabel("00:00 / 00:00", self)  # 新增的播放信息

        # 設置音量滑塊的初始值
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)

        self.play_pause_button = QPushButton("Pause")
        self.play_pause_button.clicked.connect(self.toggle_play_pause)

        self.play_load_button = QPushButton("Load")
        self.play_load_button.clicked.connect(self.load_to_play)

        layout = QVBoxLayout()
        layout.addWidget(self.video_label)
        layout.addWidget(self.slider)
        layout.addWidget(self.playback_info)  # 播放信息顯示
        layout.addWidget(QLabel("Volume:"))
        layout.addWidget(self.volume_slider)
        layout.addWidget(self.play_pause_button)
        layout.addWidget(self.play_load_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # 播放器
        self.player = MediaPlayer(self.video_path, ff_opts={'paused': False})

        # 獲取幀率並設置定時器間隔
        metadata = self.player.get_metadata()
        print(metadata)
        video_stream = metadata.get('video', [{}])[0]  # 提取第一個視頻流的數據
        #frame_rate = 18#video_stream.get('fps', 30)  # 默認幀率為 30
        frame_rate = self.get_framerate(self.video_path)
        self.frame_interval = int(1000 / frame_rate)  # 計算間隔（毫秒）

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(self.frame_interval)

        self.slider.sliderPressed.connect(self.pause_on_slider_press)
        self.slider.sliderReleased.connect(self.resume_on_slider_release)

        # 音量滑塊事件
        self.volume_slider.valueChanged.connect(self.set_volume)

    def get_framerate(self, video_path):
        try:
            probe = ffmpeg.probe(video_path)
            video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            if video_stream and 'avg_frame_rate' in video_stream:
                avg_frame_rate = video_stream['avg_frame_rate']
                if '/' in avg_frame_rate:
                    numerator, denominator = map(int, avg_frame_rate.split('/'))
                    return numerator / denominator
            return 30  # 默認返回 30fps
        except Exception as e:
            print(f"Error extracting framerate: {e}")
            return 30  # 默認值

    def stop_playback(self):
        """停止播放"""
        self.is_paused = True
        self.player.set_pause(True)
        self.timer.stop()  # 停止更新
        self.play_pause_button.setText("Play")  # 更新按鈕文字
        self.slider.setValue(0)
        self.seek()
        self.playback_info.setText("00:00 / 00:00")

    def update_frame(self):
        """更新視頻幀"""
        if self.is_paused:
            return

        frame, val = self.player.get_frame()
        if frame is not None:
            # The timestamp is contained within the frame object itself
            timestamp = frame[1]  # The timestamp is the second element of the frame
            #print(f"Frame timestamp: {timestamp}")

        # 檢查是否到達 EOF
        if val == 'eof':
            print('eof')
            self.stop_playback()
            return

        if frame:
            img, t = frame
            data = img.to_bytearray()[0]
            w, h = img.get_size()
            q_image = QImage(data, w, h, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_image)
            self.video_label.setPixmap(pixmap)

        # 獲取元數據並更新滑桿
        metadata = self.player.get_metadata()
        duration = float(metadata.get('duration') or 0)  # 默認為 0.0

        if val != 'eof' and duration > 0 and frame is not None:
            #current_time = self.player.get_pts()
            current_time = timestamp
            #pos = int(self.player.get_pts() * 100 / duration)
            pos = int(current_time * 100 / duration)
            self.slider.setValue(pos)
            self.update_playback_info(current_time, duration)

        if self.play_pause_button.text() == 'Play' and frame is not None:
            self.pause_on_slider_press()

    def toggle_play_pause(self):
        """切換播放/暫停"""
        self.is_paused = not self.is_paused
        self.player.set_pause(self.is_paused)
        if self.is_paused == False:
            self.timer.start(self.frame_interval)
        self.play_pause_button.setText("Play" if self.is_paused else "Pause")

    def pause_on_slider_press(self):
        """滑桿拖動時暫停播放"""
        self.is_paused = True
        self.slider_pressed = True
        self.player.set_pause(True)
        print('s_press')

    def resume_on_slider_release(self):
        """滑桿釋放時恢復播放"""
        self.slider_pressed = False
        self.is_paused = False
        self.player.set_pause(self.is_paused)  # 恢復到當前狀態
        if self.play_pause_button.text() == 'Play': ## Pause state.
            self.timer.start(self.frame_interval)
        self.seek()
        print('s_rel')

    def seek(self):
        """跳轉到滑桿位置"""
        position = self.slider.value()
        metadata = self.player.get_metadata()
        duration = float(metadata.get('duration') or 0)
        if duration > 0:
            new_time = position * duration / 100
            self.player.seek(new_time, relative=False)

    def set_volume(self, value):
        """設置播放器音量"""
        volume = value / 100.0  # 將滑塊值轉換為 0.0 ~ 1.0
        self.player.set_volume(volume)

    def update_playback_info(self, current_time, duration):
        """更新播放進度的文本顯示"""
        if current_time is None or duration <= 0:
            self.playback_info.setText("00:00 / 00:00")
        else:
            current_time_text = self.seconds_to_time(int(current_time))
            duration_text = self.seconds_to_time(int(duration))
            self.playback_info.setText(f"{current_time_text} / {duration_text}")

    @staticmethod
    def seconds_to_time(seconds):
        """將秒數轉換為 MM:SS 格式"""
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02}:{seconds:02}"

    def closeEvent(self, event):
        """釋放資源"""
        self.player.close_player()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    """打开文件对话框选择视频文件"""
    video_path, _ = QFileDialog.getOpenFileName(None, "Open Video File", "", 
                                                "Video Files (*.mp4 *.avi *.mkv)")
    if video_path:
        player = VideoPlayer(video_path)
        player.resize(800, 600)
        player.show()
    sys.exit(app.exec_())
