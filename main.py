import sys
import os
import json
import subprocess
import traceback
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QSlider, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QListWidget,
    QLineEdit, QCheckBox, QMessageBox, QMenuBar, QAction,
    QListWidgetItem, QDialog, QShortcut, QFrame, QScrollArea,
    QInputDialog, QColorDialog, QMenu
)
from PyQt5.QtCore import Qt, QTimer, QTime, QPoint, pyqtSignal, QMimeData
from PyQt5.QtGui import QPixmap, QImage, QKeySequence, QColor, QDrag
import cv2

class ClickableSlider(QSlider):
    clicked = pyqtSignal(QPoint)
    
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit(event.pos())

class TagManager:
    def __init__(self):
        self.tags = []
        self.shortcuts = {}
        self.tag_colors = {}
        self.available_colors = [
            "#FF9999", "#99FF99", "#9999FF", 
            "#FFFF99", "#FF99FF", "#99FFFF",
            "#FFCC99", "#CC99FF", "#FF6666",
            "#66FF66", "#6666FF"
        ]
        
    def add_tag(self, tag, shortcut=None, color=None):
        if tag not in self.tags:
            self.tags.append(tag)
            if shortcut:
                self.shortcuts[tag] = shortcut
            self.tag_colors[tag] = color if color else self.available_colors[len(self.tags) % len(self.available_colors)]
        return self

    def get_tag_color(self, tag):
        return self.tag_colors.get(tag, "#DDDDDD")
    
    def get_tags(self):
        return self.tags
    
    def get_shortcut(self, tag):
        return self.shortcuts.get(tag, None)

class DraggableButton(QPushButton):
    def __init__(self, text, parent):
        super().__init__(text, parent)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.parent = parent
        self.setCursor(Qt.OpenHandCursor)
        self.selected_tag = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent.selected_tag = self.text()
            self.drag_start_position = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return
        
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.text())
        drag.setMimeData(mime)
        
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        drag.exec_(Qt.MoveAction)
        self.setCursor(Qt.OpenHandCursor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasText():
            source = event.mimeData().text()
            target = self.text()
            self.parent.reorder_tags(source, target)
            event.acceptProposedAction()

class FootballVideoAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Football Video Analyzer Pro")
        self.setGeometry(100, 100, 1400, 900)
        self.tag_manager = TagManager()
        self.selected_tag = None
        self.setup_ui()
        self.setup_shortcuts()
        
    def setup_ui(self):
        self.create_widgets()
        self.setup_layout()
        self.setup_menu()
        self.setup_video_playback()
        self.setup_default_tags()
        
    def create_widgets(self):
        # Video widgets
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(800, 450)
        
        self.seek_slider = ClickableSlider(Qt.Horizontal)
        self.time_label = QLabel("00:00:00 / 00:00:00")
        
        # Control buttons
        self.play_button = QPushButton("▶ Play")
        self.prev_frame_button = QPushButton("⏮ Frame")
        self.next_frame_button = QPushButton("⏭ Frame")
        self.prev_minute_button = QPushButton("⏮ -1 Min")
        self.next_minute_button = QPushButton("⏭ +1 Min")
        
        # Clip controls
        self.start_clip_button = QPushButton("⏺ Set Start")
        self.end_clip_button = QPushButton("⏹ Set End")
        self.tag_input = QLineEdit()
        self.add_clip_button = QPushButton("➕ Add Clip")
        
        # Tags panel
        self.tags_container = QWidget()
        self.tags_layout = QHBoxLayout()
        self.tags_layout.setSpacing(5)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        
        # Clips list
        self.clips_list = QListWidget()
        self.export_button = QPushButton("💾 Export Selected Clips")
        
    def setup_layout(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout()
        
        # Left panel (video + controls)
        left_panel = QVBoxLayout()
        left_panel.addWidget(self.video_label)
        left_panel.addWidget(self.seek_slider)
        left_panel.addWidget(self.time_label)
        
        # Control buttons
        control_layout = QHBoxLayout()
        control_buttons = [
            self.play_button, self.prev_frame_button, 
            self.next_frame_button, self.prev_minute_button,
            self.next_minute_button
        ]
        for btn in control_buttons:
            control_layout.addWidget(btn)
        left_panel.addLayout(control_layout)
        
        # Clip controls
        clip_layout = QHBoxLayout()
        clip_controls = [
            self.start_clip_button, self.end_clip_button,
            self.tag_input, self.add_clip_button
        ]
        for control in clip_controls:
            clip_layout.addWidget(control)
        left_panel.addLayout(clip_layout)
        
        # Right panel (tags + clips list)
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(10, 0, 0, 0)
        
        # Tags section
        right_panel.addWidget(QLabel("Available Tags:"))
        self.update_tags_buttons()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.tags_container)
        right_panel.addWidget(scroll)
        
        # Clips list
        right_panel.addWidget(QLabel("Clips List:"))
        right_panel.addWidget(self.clips_list)
        right_panel.addWidget(self.export_button)
        
        # Combine panels
        main_layout.addLayout(left_panel, 70)
        main_layout.addLayout(right_panel, 30)
        central_widget.setLayout(main_layout)

    def new_project(self):
        """Reset all variables to start a new project"""
        if hasattr(self, 'cap') and self.cap:
            self.cap.release()
        
        self.video_path = ""
        self.total_frames = 0
        self.current_frame = 0
        self.playing = False
        self.clips = []
        self.clips_list.clear()
        self.video_label.clear()
        self.time_label.setText("00:00:00 / 00:00:00")
        self.seek_slider.setValue(0)
        QMessageBox.information(self, "New Project", "New project created successfully")

    def open_video(self):
        """Open a video file"""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Open Video", 
            "", 
            "Video Files (*.mp4 *.avi *.mov);;All Files (*)"
        )
        
        if path:
            self.video_path = path
            self.cap = cv2.VideoCapture(path)
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.seek_slider.setMaximum(self.total_frames)
            self.current_frame = 0
            self.update_frame()

    def load_data(self):
        """Load saved project data"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Project Data",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if path:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.clips = data.get('clips', [])
                    self.update_clips_list()
                    QMessageBox.information(self, "Success", "Project data loaded")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load data: {str(e)}")

    def save_data(self):
        """Save project data to file"""
        if not self.video_path:
            QMessageBox.warning(self, "Warning", "No video is loaded")
            return
            
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project Data",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if path:
            data = {
                'video_path': self.video_path,
                'clips': self.clips
            }
            
            try:
                with open(path, 'w') as f:
                    json.dump(data, f)
                QMessageBox.information(self, "Success", "Project data saved")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save data: {str(e)}")


    def setup_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("📁 File")
        actions = [
            ("🆕 New Project", self.new_project),
            ("🎬 Open Video...", self.open_video),
            ("📂 Load Data...", self.load_data),
            ("💾 Save Data As...", self.save_data),
            ("🚪 Exit", self.close)
        ]
        for text, slot in actions:
            action = QAction(text, self)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        
        # Tags menu
        tags_menu = menubar.addMenu("🏷 Tags")
        add_tag_action = QAction("➕ Add New Tag", self)
        add_tag_action.triggered.connect(self.add_new_tag)
        tags_menu.addAction(add_tag_action)

    def frames_to_time(self, frames):
        """Convert frame number to HH:MM:SS format"""
        seconds = int(frames / self.fps) if self.fps > 0 else 0
        return QTime(0, 0, 0).addSecs(seconds).toString("HH:mm:ss")

    def update_frame(self):
        if self.cap and self.playing:
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                self.seek_slider.setValue(self.current_frame)
                
                # Convert frame to QImage and display
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                qimg = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888)
                self.video_label.setPixmap(QPixmap.fromImage(qimg))
                
                # Update time label
                current_time = self.frames_to_time(self.current_frame)
                total_time = self.frames_to_time(self.total_frames)
                self.time_label.setText(f"{current_time} / {total_time}")

    def setup_video_playback(self):
        self.cap = None
        self.video_path = ""
        self.total_frames = 0
        self.fps = 30
        self.current_frame = 0
        self.playing = False
        self.clips = []
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        
        # Connect signals
        self.play_button.clicked.connect(self.toggle_play)
        self.prev_frame_button.clicked.connect(self.prev_frame)
        self.next_frame_button.clicked.connect(self.next_frame)
        self.start_clip_button.clicked.connect(self.set_clip_start)
        self.end_clip_button.clicked.connect(self.set_clip_end)
        self.add_clip_button.clicked.connect(self.add_clip)
        self.export_button.clicked.connect(self.export_clips)
        self.clips_list.itemDoubleClicked.connect(self.edit_clip)
        self.seek_slider.sliderMoved.connect(self.seek_video)
        self.seek_slider.clicked.connect(self.slider_clicked)
        
    def setup_default_tags(self):
        self.tag_manager = TagManager()
        default_tags = [
            ("DefCorner", "Ctrl+1"),
            ("TraAttToDef", "Ctrl+2"),
            ("CounterAttack", "Ctrl+3"),
            ("SetPiece", "Ctrl+4"),
            ("Goal", "Ctrl+5")
        ]
        for tag, shortcut in default_tags:
            self.tag_manager.add_tag(tag, shortcut)
    
    def setup_shortcuts(self):
        # Play/Pause with Space
        QShortcut(QKeySequence("Space"), self, self.toggle_play)
        
        # Frame navigation
        QShortcut(QKeySequence(Qt.Key_Left), self, self.prev_frame)
        QShortcut(QKeySequence(Qt.Key_Right), self, self.next_frame)
        
        # Minute navigation
        QShortcut(QKeySequence("Shift+Left"), self, lambda: self.jump_time(-60))
        QShortcut(QKeySequence("Shift+Right"), self, lambda: self.jump_time(60))
        
        # Tag shortcuts
        for tag in self.tag_manager.get_tags():
            if shortcut := self.tag_manager.get_shortcut(tag):
                QShortcut(QKeySequence(shortcut), self, lambda t=tag: self.tag_input.setText(t))

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Video Files (*.mp4 *.avi *.mov)")
        if path:
            self.video_path = path
            self.cap = cv2.VideoCapture(path)
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.seek_slider.setMaximum(self.total_frames)
            self.update_frame()

    def add_clip(self):
        if hasattr(self, 'clip_start') and hasattr(self, 'clip_end'):
            tag = self.tag_input.text()
            if tag:
                self.clips.append({
                    'start': self.clip_start,
                    'end': self.clip_end,
                    'tag': tag
                })
                self.clips_list.addItem(f"{tag}: {self.clip_start}-{self.clip_end}")
                delattr(self, 'clip_start')
                delattr(self, 'clip_end')

    def closeEvent(self, event):
        if hasattr(self, 'cap') and self.cap:
            self.cap.release()
        event.accept()

    # ... (بقیه متدها مانند قبل با همان پیاده‌سازی) ...
    def update_tags_buttons(self):
        """به‌روزرسانی دکمه‌های تگ در پنل سمت راست"""
        # پاک کردن دکمه‌های موجود
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # ایجاد دکمه‌های جدید برای تگ‌ها
        for tag in self.tag_manager.get_tags():
            btn = DraggableButton(tag, self)
            color = self.tag_manager.get_tag_color(tag)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 1px solid #888;
                    padding: 5px;
                    border-radius: 4px;
                    min-width: 60px;
                    margin: 2px;
                }}
                QPushButton:hover {{
                    background-color: {self.lighter_color(color)};
                }}
            """)
            
            # تنظیم tooltip برای شورتکات
            if shortcut := self.tag_manager.get_shortcut(tag):
                btn.setToolTip(f"Shortcut: {shortcut}")
            
            # اتصال رویداد کلیک
            btn.clicked.connect(lambda checked, t=tag: self.tag_input.setText(t))
            self.tags_layout.addWidget(btn)
        
        # افزودن دکمه تغییر رنگ
        color_btn = QPushButton("🎨")
        color_btn.setToolTip("Change tag color")
        color_btn.clicked.connect(self.change_tag_color)
        self.tags_layout.addWidget(color_btn)
        
        # افزودن فضای خالی
        self.tags_layout.addStretch()
        self.tags_container.setLayout(self.tags_layout)
    
    def lighter_color(self, hex_color, factor=0.3):
        """تولید رنگ روشن‌تر برای حالت hover"""
        rgb = [int(hex_color[i:i+2], 16) for i in (1, 3, 5)]
        lighter = [min(255, val + int((255 - val) * factor)) for val in rgb]
        return f"#{lighter[0]:02X}{lighter[1]:02X}{lighter[2]:02X}"
    
    def change_tag_color(self):
        """تغییر رنگ تگ انتخاب شده"""
        if hasattr(self, 'selected_tag'):
            color = QColorDialog.getColor(
                QColor(self.tag_manager.get_tag_color(self.selected_tag)),
                self,
                "Choose Tag Color"
            )
            if color.isValid():
                self.tag_manager.tag_colors[self.selected_tag] = color.name()
                self.update_tags_buttons()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = FootballVideoAnalyzer()
    window.show()
    sys.exit(app.exec_())
