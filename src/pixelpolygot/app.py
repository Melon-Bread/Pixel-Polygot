"""
Reads text from game screenshot and translate to English.
"""
import importlib.metadata
import sys
import os
import json
import base64
from pathlib import Path
import time
from threading import Thread

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer, Signal, Slot, QFileSystemWatcher
import openai

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "api_key": "<YOUR_API_KEY_HERE>",
    "api_url": "http://localhost:9009",
    "model": "qwen2.5-vl-7b-instruct",
    "prompt": "What is the Japanese text in this image and what does it mean in English?"
}


class FileWatcher(QtCore.QObject):
    file_changed = Signal(str)

    def __init__(self, directory):
        super().__init__()
        self.watcher = QFileSystemWatcher()
        self.directory = directory
        self.watcher.addPath(directory)
        self.watcher.directoryChanged.connect(self.on_directory_changed)
        self.known_files = set(self.get_image_files())
        print(f"Watching {directory} for changes")

    def get_image_files(self):
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        return [
            os.path.join(self.directory, f) for f in os.listdir(self.directory)
            if os.path.isfile(os.path.join(self.directory, f)) and 
            os.path.splitext(f)[1].lower() in image_extensions
        ]

    def on_directory_changed(self, path):
        current_files = set(self.get_image_files())
        new_files = current_files - self.known_files
        
        if new_files:
            # Sort by creation time to get the newest
            newest_file = sorted(new_files, key=os.path.getctime, reverse=True)[0]
            self.file_changed.emit(newest_file)
            print(f"New image detected: {newest_file}")
        
        self.known_files = current_files


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        form_layout = QtWidgets.QFormLayout()
        
        # API Key
        self.api_key_input = QtWidgets.QLineEdit(self.config["api_key"])
        form_layout.addRow("API Key:", self.api_key_input)
        
        # API URL
        self.api_url_input = QtWidgets.QLineEdit(self.config["api_url"])
        form_layout.addRow("API URL:", self.api_url_input)
        
        # Model
        self.model_input = QtWidgets.QLineEdit(self.config["model"])
        form_layout.addRow("Model:", self.model_input)
        
        # Prompt
        self.prompt_input = QtWidgets.QTextEdit()
        self.prompt_input.setPlainText(self.config["prompt"])
        self.prompt_input.setMinimumHeight(100)
        form_layout.addRow("Prompt:", self.prompt_input)
        
        # Watch Directory
        self.directory_layout = QtWidgets.QHBoxLayout()
        self.directory_input = QtWidgets.QLineEdit(self.config.get("watch_directory", ""))
        self.directory_button = QtWidgets.QPushButton("Browse...")
        self.directory_button.clicked.connect(self.select_directory)
        self.directory_layout.addWidget(self.directory_input)
        self.directory_layout.addWidget(self.directory_button)
        form_layout.addRow("Watch Directory:", self.directory_layout)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def select_directory(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Directory to Watch", self.directory_input.text()
        )
        if directory:
            self.directory_input.setText(directory)
    
    def get_settings(self):
        return {
            "api_key": self.api_key_input.text(),
            "api_url": self.api_url_input.text(),
            "model": self.model_input.text(),
            "prompt": self.prompt_input.toPlainText(),
            "watch_directory": self.directory_input.text()
        }


class PixelPolygot(QtWidgets.QMainWindow):
    api_response_ready = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.current_image_path = None
        self.config = self.load_config()
        self.init_ui()
        self.setup_watcher()
    
    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            else:
                return DEFAULT_CONFIG.copy()
        except Exception as e:
            print(f"Error loading config: {e}")
            return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def init_ui(self):
        self.setWindowTitle("PixelPolygot")
        self.setWindowIcon(QIcon("resources/PixelPolygot.png"))
        self.resize(800, 600)
        
        # Central widget
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        
        # Image display
        self.image_label = QtWidgets.QLabel("No image loaded")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumHeight(300)
        self.image_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ddd;")
        
        # Text output
        self.output_text = QtWidgets.QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(200)
        font = QtGui.QFont("Segoe UI", 10)
        self.output_text.setFont(font)
        
        # Regenerate button
        self.regenerate_button = QtWidgets.QPushButton("Regenerate Response")
        self.regenerate_button.clicked.connect(self.regenerate_response)
        self.regenerate_button.setEnabled(False)
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
        # Add widgets to layout
        main_layout.addWidget(self.image_label, 3)
        main_layout.addWidget(self.output_text, 2)
        main_layout.addWidget(self.regenerate_button)
        
        # Menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        
        # Open image action
        open_action = QtGui.QAction("Open Image", self)
        open_action.triggered.connect(self.open_image)
        file_menu.addAction(open_action)
        
        # Settings action
        settings_action = QtGui.QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)
        
        # Exit action
        exit_action = QtGui.QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Connect signals
        self.api_response_ready.connect(self.update_output_text)
        
        self.show()
    
    def setup_watcher(self):
        # Only set up watcher if directory is configured
        if "watch_directory" in self.config and os.path.exists(self.config["watch_directory"]):
            self.watcher = FileWatcher(self.config["watch_directory"])
            self.watcher.file_changed.connect(self.on_new_image)
            self.statusBar().showMessage(f"Watching {self.config['watch_directory']} for new images")
        else:
            self.statusBar().showMessage("No watch directory configured. Go to Settings to set one.")
    
    def show_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            old_directory = self.config.get("watch_directory", "")
            self.config = dialog.get_settings()
            self.save_config()
            
            # If directory changed, update the watcher
            if old_directory != self.config["watch_directory"]:
                self.setup_watcher()
    
    def open_image(self):
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if file_name:
            self.process_image(file_name)
    
    @Slot(str)
    def on_new_image(self, file_path):
        self.process_image(file_path)
    
    def process_image(self, file_path):
        self.current_image_path = file_path
        
        # Update image display
        pixmap = QtGui.QPixmap(file_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.image_label.width(), self.image_label.height(),
                QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            )
            self.image_label.setPixmap(pixmap)
            self.regenerate_button.setEnabled(True)
            
            # Send to API
            self.statusBar().showMessage(f"Processing image: {os.path.basename(file_path)}")
            self.send_to_api(file_path)
        else:
            self.statusBar().showMessage(f"Failed to load image: {os.path.basename(file_path)}")
    
    def send_to_api(self, file_path):
        # Avoid blocking UI
        self.output_text.setPlainText("Processing image with API...")
        
        # Run in a separate thread
        thread = Thread(target=self._api_request, args=(file_path,))
        thread.daemon = True
        thread.start()
    
    def _api_request(self, file_path):
        try:
            # Create a fresh client for each request to ensure we use the latest config
            client = openai.OpenAI(
                api_key=self.config["api_key"],
                base_url=self.config["api_url"]
            )
            
            # Debug info
            print(f"Using API URL: {self.config['api_url']}")
            print(f"Using model: {self.config['model']}")
            
            # Determine model type
            model_name = self.config["model"].lower()
            is_qwen = "qwen" in model_name
            is_dashscope = "dashscope" in self.config["api_url"].lower()
            use_streaming = is_qwen or model_name.endswith("-omni-7b")
            
            try:
                # Prepare image - read as binary data
                with open(file_path, "rb") as image_file:
                    image_data = image_file.read()
                
                # For Qwen/DashScope models, encode image as base64 string
                image_base64 = base64.b64encode(image_data).decode("utf-8")
                
                # Structure image data correctly based on the model/API
                if is_qwen or is_dashscope:
                    # For DashScope/Qwen models
                    image_url = {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                else:
                    # For OpenAI and other models with 'detail' parameter
                    image_url = {
                        "url": f"data:image/jpeg;base64,{image_base64}",
                        "detail": "high"
                    }
                
                # Create system message
                system_message = {"role": "system", "content": "You are a helpful assistant."}
                
                # Create user message with text and image
                user_message = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.config["prompt"]},
                        {"type": "image_url", "image_url": image_url}
                    ]
                }
                
                # Make API request
                if use_streaming:
                    # Streaming request
                    response = client.chat.completions.create(
                        model=self.config["model"],
                        messages=[system_message, user_message],
                        max_tokens=1000,
                        stream=True
                    )
                    
                    # Process streaming response
                    full_response = ""
                    for chunk in response:
                        if chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_response += content
                            # Update UI with partial response
                            self.api_response_ready.emit(full_response)
                    
                    # Final update if needed
                    if not full_response:
                        self.api_response_ready.emit("No response content received.")
                
                else:
                    # Non-streaming request
                    response = client.chat.completions.create(
                        model=self.config["model"],
                        messages=[system_message, user_message],
                        max_tokens=1000
                    )
                    
                    # Get response content
                    result = response.choices[0].message.content
                    self.api_response_ready.emit(result)
                
            except Exception as e:
                error_message = f"API Request Error: {str(e)}"
                print(error_message)
                self.api_response_ready.emit(error_message)
            
        except Exception as e:
            error_message = f"Error: {str(e)}"
            print(error_message)
            self.api_response_ready.emit(error_message)
    
    @Slot(str)
    def update_output_text(self, text):
        self.output_text.setPlainText(text)
        self.statusBar().showMessage("Response received from API")
    
    def regenerate_response(self):
        if self.current_image_path:
            self.send_to_api(self.current_image_path)
            self.statusBar().showMessage("Regenerating response...")
    
    def resizeEvent(self, event):
        # Update image if there is one to make sure it scales properly
        if self.current_image_path and hasattr(self, 'image_label'):
            pixmap = QtGui.QPixmap(self.current_image_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    self.image_label.width(), self.image_label.height(),
                    QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
                )
                self.image_label.setPixmap(pixmap)
        super().resizeEvent(event)


def main():
    # Find the name of the module that was used to start the app
    app_module = sys.modules["__main__"].__package__
    # Retrieve the app's metadata
    metadata = importlib.metadata.metadata(app_module)
    QtWidgets.QApplication.setApplicationName(metadata["Formal-Name"])
    app = QtWidgets.QApplication(sys.argv)
    main_window = PixelPolygot()
    sys.exit(app.exec())