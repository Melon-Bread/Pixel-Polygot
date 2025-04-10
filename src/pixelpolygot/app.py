"""
Reads text from game screenshot and translate to English.
"""

import importlib.metadata
import sys
import os
import sys # Keep sys for main()
from pathlib import Path

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QSizePolicy # Added QComboBox, QHBoxLayout, QSizePolicy
from PySide6.QtGui import QIcon, QAction # Explicitly import QAction
from PySide6.QtCore import Signal, Slot, QTimer

# Import new modules
from . import config
from . import file_watcher
from . import settings_dialog
from . import api_client


class PixelPolygot(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()
        self.current_image_path = None
        self.config = config.load_config()
        self.api_client = api_client.ApiClient(self.config) # Instantiate ApiClient
        self.init_ui()
        self.setup_watcher()
        self.connect_signals() # Connect signals after UI is initialized


    def init_ui(self):
        self.setWindowTitle("PixelPolygot")
        # Try loading icon relative to this file's location
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "PixelPolygot.png")
        if os.path.exists(icon_path):
             self.setWindowIcon(QIcon(icon_path))
        else:
             print(f"Warning: Icon file not found at {icon_path}")
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
        self.image_label.setStyleSheet(
            "background-color: #f0f0f0; border: 1px solid #ddd;"
        )

        # Text output
        self.output_text = QtWidgets.QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(200)
        font = QtGui.QFont("Segoe UI", 10)
        self.output_text.setFont(font)

        # Prompt Dropdown
        self.prompt_dropdown = QtWidgets.QComboBox()
        self.prompt_dropdown.setToolTip("Select a system prompt to use for the API request.")
        self._populate_prompts_dropdown() # Populate the dropdown

        # Regenerate button
        self.regenerate_button = QtWidgets.QPushButton("Regenerate Response")
        self.regenerate_button.setToolTip(
            "Resend the current image to the API.\nUseful for if API fails or bad response."
        )
        self.regenerate_button.clicked.connect(self.regenerate_response)
        self.regenerate_button.setEnabled(False)
        # Make the button expand horizontally
        self.regenerate_button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        # Button Layout (Horizontal)
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.prompt_dropdown)
        button_layout.addWidget(self.regenerate_button)
        # button_layout.addStretch(1) # Removed stretch to allow button expansion

        # Status bar
        self.statusBar().showMessage("Ready")

        # Add widgets to layout
        main_layout.addWidget(self.image_label, 3)
        main_layout.addWidget(self.output_text, 2)
        # main_layout.addWidget(self.regenerate_button) # Replaced by button_layout
        main_layout.addLayout(button_layout) # Add the horizontal layout

        # Menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        # Open image action
        open_action = QAction("Open Image", self) # Use imported QAction
        open_action.triggered.connect(self.open_image)
        file_menu.addAction(open_action)

        # Settings action
        settings_action = QAction("Settings", self) # Use imported QAction
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)

        # Exit action
        exit_action = QAction("Exit", self) # Use imported QAction
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)


    def _populate_prompts_dropdown(self):
        """Populates the prompt dropdown with files from the prompts directory."""
        self.prompt_dropdown.clear() # Clear existing items
        prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
        found_prompts = False
        if os.path.isdir(prompts_dir):
            try:
                # Sort files alphabetically for consistent order
                for filename in sorted(os.listdir(prompts_dir)):
                    full_path = os.path.join(prompts_dir, filename)
                    if os.path.isfile(full_path):
                        # Use filename without extension as display text
                        display_name, _ = os.path.splitext(filename)
                        # Store the full path as data associated with the item
                        self.prompt_dropdown.addItem(display_name, full_path)
                        found_prompts = True
            except OSError as e:
                print(f"Error reading prompts directory {prompts_dir}: {e}")
                self.statusBar().showMessage(f"Error reading prompts directory: {e}")

        if not found_prompts:
            # Add Default item with None data if no prompts found or dir missing/error
            self.prompt_dropdown.addItem("Default", None)


    def connect_signals(self):
        """Connect signals from components."""
        self.api_client.api_response_ready.connect(self.update_output_text) # For final response
        self.api_client.api_partial_response.connect(self.handle_partial_response) # For streaming updates
        self.api_client.api_error.connect(self.handle_api_error)
        # Connect file watcher signal if watcher exists
        if hasattr(self, 'watcher') and self.watcher:
             self.watcher.file_changed.connect(self.on_new_image)

    def setup_watcher(self):
        # Reset watcher if it exists
        if hasattr(self, 'watcher') and self.watcher:
            self.watcher.deleteLater() # Clean up old watcher
            self.watcher = None

        watch_dir = self.config.get("watch_directory")
        if watch_dir and os.path.isdir(watch_dir): # Check if it's a directory
            try:
                self.watcher = file_watcher.FileWatcher(watch_dir)
                self.statusBar().showMessage(
                     f"Watching {watch_dir} for new images"
                )
            except Exception as e:
                 print(f"Error initializing file watcher for {watch_dir}: {e}")
                 self.statusBar().showMessage(f"Error starting watcher for {watch_dir}")
                 self.watcher = None # Ensure watcher is None on error
        elif watch_dir:
             self.statusBar().showMessage(f"Watch directory '{watch_dir}' not found or invalid.")
        else: # Covers case where watch_dir is empty or invalid path from above
             self.statusBar().showMessage(
                 "No watch directory configured or directory invalid. Go to Settings to set one."
             )

    def show_settings(self):
        # Pass a copy of the config to avoid modifying it if Cancel is clicked
        dialog = settings_dialog.SettingsDialog(self.config.copy(), self)
        if dialog.exec():
            old_directory = self.config.get("watch_directory", "")
            self.config = dialog.get_settings()
            config.save_config(self.config) # Use config module's save function
            self.api_client.config = self.config # Update ApiClient's config

            # If directory changed, update the watcher
            new_directory = self.config.get("watch_directory", "")
            if old_directory != new_directory:
                self.setup_watcher()
                # Reconnect signal if watcher was created
                if hasattr(self, 'watcher') and self.watcher:
                    # Reconnect the signal from the new watcher instance
                    self.watcher.file_changed.connect(self.on_new_image)


    def open_image(self):
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if file_name:
            self.process_image(file_name)

    @Slot(str)
    def on_new_image(self, file_path):
        # Check if file still exists and is accessible
        if os.path.exists(file_path) and os.access(file_path, os.R_OK):
            try:
                self.process_image(file_path)
            except Exception as e:
                self.statusBar().showMessage(f"Error processing new image: {str(e)}")
                print(f"Error processing new image: {e}")
        else:
            self.statusBar().showMessage(
                f"File no longer exists or inaccessible: {os.path.basename(file_path)}"
            )

    def process_image(self, file_path):
        self.current_image_path = file_path

        # Update image display
        pixmap = QtGui.QPixmap(file_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.image_label.width(),
                self.image_label.height(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            self.image_label.setPixmap(pixmap)
            self.regenerate_button.setEnabled(True)

            # Send to API
            self.statusBar().showMessage(
                f"Processing image: {os.path.basename(file_path)}"
            )
            self.send_to_api(file_path)
        else:
            self.statusBar().showMessage(
                f"Failed to load image: {os.path.basename(file_path)}"
            )

    def send_to_api(self, file_path):
        """Initiates the API request using the ApiClient, including selected prompt."""
        # Clear the output text box before starting a new request
        self.output_text.clear()
        # self.output_text.setPlainText("Processing image with API...") # Removed - partial updates will handle this
        self.statusBar().showMessage(f"Sending {os.path.basename(file_path)} to API...")

        prompt_content = None
        prompt_path = self.prompt_dropdown.currentData() # Get full path from data

        if prompt_path and os.path.exists(prompt_path):
            try:
                # Specify UTF-8 encoding for broader compatibility
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_content = f.read()
                # Optional: Log which prompt is being used
                print(f"Using prompt: {os.path.basename(prompt_path)}")
            except IOError as e:
                error_msg = f"Error reading prompt file {os.path.basename(prompt_path)}: {e}"
                print(error_msg)
                self.statusBar().showMessage(error_msg)
                # Decide if you want to proceed without prompt or stop
                # Proceeding without prompt for now:
                prompt_content = None
            except Exception as e: # Catch other potential errors like decoding errors
                error_msg = f"Unexpected error reading prompt {os.path.basename(prompt_path)}: {e}"
                print(error_msg)
                self.statusBar().showMessage(error_msg)
                prompt_content = None
        elif prompt_path:
             # Path stored but file doesn't exist (maybe deleted after population?)
             error_msg = f"Prompt file not found: {os.path.basename(prompt_path)}"
             print(error_msg)
             self.statusBar().showMessage(error_msg)
             # Ensure prompt_content is None if file not found
             prompt_content = None
        # If prompt_path was None (e.g., "Default" selected), prompt_content remains None

        # Pass prompt_content (which might be None) to the API client method
        # Ensure the API client method is updated to accept this keyword argument
        self.api_client.process_image_in_thread(file_path, prompt_content=prompt_content)


    @Slot(str)
    def handle_api_error(self, error_message):
        """Handles errors emitted by the ApiClient."""
        self.output_text.setPlainText(f"Error: {error_message}")
        self.statusBar().showMessage(f"API Error: {error_message[:100]}") # Show truncated error


    @Slot(str)
    def handle_partial_response(self, text):
        """Handles partial updates during streaming, using plain text."""
        self.output_text.setPlainText(text)
        # Optionally update status bar during streaming
        # self.statusBar().showMessage("Receiving response...")

    @Slot(str)
    def update_output_text(self, text):
        self.output_text.setMarkdown(text)
        # Check if text starts with "Error:" to provide better status
        if text.startswith("Error:"):
             self.statusBar().showMessage("API Error occurred")
        else:
             self.statusBar().showMessage("Response received from API")

    def regenerate_response(self):
        if self.current_image_path:
            self.send_to_api(self.current_image_path)
            self.statusBar().showMessage("Regenerating response...")

    def resizeEvent(self, event):
        # Update image if there is one to make sure it scales properly
        if self.current_image_path and hasattr(self, "image_label"):
            pixmap = QtGui.QPixmap(self.current_image_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    self.image_label.width(),
                    self.image_label.height(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
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
    main_window.show()
    sys.exit(app.exec())

