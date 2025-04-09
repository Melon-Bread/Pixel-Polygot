import os
import time
from PySide6 import QtCore
from PySide6.QtCore import QTimer, Signal, Slot, QFileSystemWatcher


class FileWatcher(QtCore.QObject):
    file_changed = Signal(str)

    def __init__(self, directory):
        super().__init__()
        self.watcher = QFileSystemWatcher()
        self.directory = directory
        self.watcher.addPath(directory)
        self.watcher.directoryChanged.connect(self.on_directory_changed)
        self.known_files = set(self.get_image_files())
        self.processing_timer = QTimer()
        self.processing_timer.setSingleShot(True)
        self.processing_timer.timeout.connect(self.process_new_files)
        print(f"Watching {directory} for changes")

    def get_image_files(self):
        image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]
        try:
            return [
                os.path.join(self.directory, f)
                for f in os.listdir(self.directory)
                if os.path.isfile(os.path.join(self.directory, f))
                and os.path.splitext(f)[1].lower() in image_extensions
            ]
        except FileNotFoundError:
            print(f"Error: Watch directory not found: {self.directory}")
            return []
        except Exception as e:
            print(f"Error listing image files in {self.directory}: {e}")
            return []

    def on_directory_changed(self, path):
        # Start a timer to delay processing by a short amount
        # This allows the screenshot to finish saving
        self.processing_timer.start(500)  # 500ms delay

    def process_new_files(self):
        try:
            current_files = set(self.get_image_files())
            new_files = current_files - self.known_files

            if new_files:
                # Sort by creation time to get the newest
                newest_file = sorted(new_files, key=os.path.getctime, reverse=True)[0]

                # Verify file is not empty and accessible
                if os.path.exists(newest_file) and os.path.getsize(newest_file) > 0:
                    # Additional small delay to ensure file is fully written
                    time.sleep(0.2)
                    self.file_changed.emit(newest_file)
                    print(f"New image detected: {newest_file}")
                elif os.path.exists(newest_file): # Check if it exists but might be empty
                    # If file appears to be empty, try again after a delay
                    QTimer.singleShot(500, lambda: self.check_file_again(newest_file))

            self.known_files = current_files
        except Exception as e:
            print(f"Error processing new files: {e}")

    def check_file_again(self, file_path):
        # Second attempt to read the file after a delay
        try:
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                self.file_changed.emit(file_path)
                print(f"New image detected (retry): {file_path}")
                # Update known_files here as well, in case it was missed
                self.known_files = set(self.get_image_files())
        except Exception as e:
            print(f"Error in second attempt to read file: {e}")