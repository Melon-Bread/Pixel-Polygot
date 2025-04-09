from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QCheckBox, QHBoxLayout, QTextEdit, QPushButton, QDialogButtonBox, QFileDialog

# Import default config for the restore defaults functionality
from .config import DEFAULT_CONFIG


class SettingsDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.config = current_config  # Use the passed current config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        # API Type
        self.api_type_combo = QComboBox()
        self.api_type_combo.addItems(["OpenAI", "Ollama"])
        # Use current_config to set initial value
        self.api_type_combo.setCurrentText(
            self.config.get("api_type", DEFAULT_CONFIG["api_type"]).title()
        )
        self.api_type_combo.setToolTip(
            "Select the type of API to use:\nOpenAI - For OpenAI compatible APIs\nOllama - For local Ollama instance"
        )
        form_layout.addRow("API Type:", self.api_type_combo)

        # API URL
        self.api_url_input = QLineEdit(self.config.get("api_url", DEFAULT_CONFIG["api_url"]))
        self.api_url_input.setToolTip(
            "Must be a OpenAI compatabile API for the image to send."
        )
        form_layout.addRow("API URL:", self.api_url_input)

        # API Key
        self.api_key_input = QLineEdit(self.config.get("api_key", DEFAULT_CONFIG["api_key"]))
        self.api_key_input.setToolTip(
            "Your unique API key from your provider.\nCan be left blank if self hosting typically."
        )
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_api_key_checkbox = QCheckBox("Show")
        self.show_api_key_checkbox.toggled.connect(self.toggle_api_key_echo)
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(self.api_key_input)
        api_key_layout.addWidget(self.show_api_key_checkbox)
        form_layout.addRow("API Key:", api_key_layout)

        # Model
        self.model_input = QLineEdit(self.config.get("model", DEFAULT_CONFIG["model"]))
        self.model_input.setToolTip(
            "Single name of the model you to send the image to.\nSee you API docs for a list of model names that support vision."
        )
        form_layout.addRow("Model:", self.model_input)

        # Prompt
        self.prompt_input = QTextEdit()
        self.prompt_input.setToolTip(
            "Instructions that get sent to the model.\n'Better' prompt, 'better' results."
        )
        self.prompt_input.setPlainText(self.config.get("prompt", DEFAULT_CONFIG["prompt"]))
        self.prompt_input.setMinimumHeight(100)
        form_layout.addRow("Prompt:", self.prompt_input)

        # Watch Directory
        self.directory_layout = QHBoxLayout()
        self.directory_input = QLineEdit(
            self.config.get("watch_directory", DEFAULT_CONFIG["watch_directory"])
        )
        self.directory_input.setToolTip(
            "Only watches when new images get placed for auto upload/translation."
        )
        self.directory_button = QPushButton("Browse...")
        self.directory_button.clicked.connect(self.select_directory)
        self.directory_layout.addWidget(self.directory_input)
        self.directory_layout.addWidget(self.directory_button)
        form_layout.addRow("Watch Directory:", self.directory_layout)

        layout.addLayout(form_layout)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok
            | QDialogButtonBox.Cancel
            | QDialogButtonBox.RestoreDefaults
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            self.restore_defaults
        )
        layout.addWidget(button_box)

    def toggle_api_key_echo(self, checked):
        if checked:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory to Watch", self.directory_input.text()
        )
        if directory:
            self.directory_input.setText(directory)

    def restore_defaults(self):
        """Reset all settings to their default values."""
        # Use imported DEFAULT_CONFIG
        self.api_type_combo.setCurrentText(DEFAULT_CONFIG["api_type"].title())
        self.api_url_input.setText(DEFAULT_CONFIG["api_url"])
        self.api_key_input.setText(DEFAULT_CONFIG["api_key"])
        self.model_input.setText(DEFAULT_CONFIG["model"])
        self.prompt_input.setPlainText(DEFAULT_CONFIG["prompt"])
        self.directory_input.setText(DEFAULT_CONFIG["watch_directory"])

    def get_settings(self):
        return {
            "api_type": self.api_type_combo.currentText().lower(),
            "api_url": self.api_url_input.text(),
            "api_key": self.api_key_input.text(), # Moved api_key after api_url
            "model": self.model_input.text(),
            "prompt": self.prompt_input.toPlainText(),
            "watch_directory": self.directory_input.text(),
        }