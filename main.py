import sys
import queue
from pathlib import Path
from tempfile import TemporaryDirectory

from loguru import logger
from mokuro import MokuroGenerator
from mokuro.volume import VolumeCollection
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QHBoxLayout

update_command_output = queue.Queue()
update_current_volume = queue.Queue()
finished_processing = queue.Queue()

class WorkerThread(QtCore.QThread):
    def __init__(self, vc, parent=None):
        super().__init__(parent)
        self.vc = vc

    def run(self):
        try:
            pretrained_model_name_or_path = "kha-white/manga-ocr-base"
            mg = MokuroGenerator(
                pretrained_model_name_or_path=pretrained_model_name_or_path,
                force_cpu=False,
                disable_ocr=False,
            )
            with TemporaryDirectory() as tmp_dir:
                tmp_dir = Path(tmp_dir)

                num_successful = 0
                for i, volume in enumerate(self.vc):
                    update_command_output.put(
                        f"Processing {i + 1}/{len(self.vc)}: {volume.path_in}"
                    )
                    update_current_volume.put(
                        f"Processing {i + 1}/{len(self.vc)}: {volume.path_in}"
                    )

                    try:
                        volume.unzip(tmp_dir)
                        mg.process_volume(volume, ignore_errors=False, no_cache=False)
                    except Exception as e:
                        update_command_output.put(f"Error while processing {volume.path_in}: {str(e)}")
                    else:
                        num_successful += 1

                finished_processing.put(
                    f"Processed successfully: {num_successful}/{len(self.vc)}"
                )
        except Exception as e:
            update_command_output.put(f"\n\n\nError while processing {e}\n\n\n")


class Ui_MainWindow(object):
    def __init__(self):
        self.volumes_processed = 0
        self.per_volume_percentage = 0

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.setWindowTitle("Mokuro")
        MainWindow.resize(800, 600)
        self.central_widget = QtWidgets.QWidget(MainWindow)
        self.central_widget.setObjectName("centralwidget")
        MainWindow.setCentralWidget(self.central_widget)
        self.central_layout = QtWidgets.QVBoxLayout(self.central_widget)

        button_layout = QtWidgets.QHBoxLayout()
        self.show_select_folder_btn = QtWidgets.QPushButton(
            "Select manga folder", self.central_widget
        )
        self.show_select_folder_btn.clicked.connect(self.select_folder)
        font = QtGui.QFont()
        font.setPointSize(12)
        self.show_select_folder_btn.setFont(font)
        self.show_select_folder_btn.setFixedSize(181, 51)

        self.show_select_files_btn = QtWidgets.QPushButton(
            "Select manga files", self.central_widget
        )
        self.show_select_files_btn.clicked.connect(self.select_files)
        font = QtGui.QFont()
        font.setPointSize(12)
        self.show_select_files_btn.setFont(font)
        self.show_select_files_btn.setFixedSize(181, 51)

        button_layout.addWidget(
            self.show_select_files_btn, alignment=QtCore.Qt.AlignCenter
        )
        button_layout.addWidget(
            self.show_select_folder_btn, alignment=QtCore.Qt.AlignCenter
        )
        self.central_layout.addLayout(button_layout)
        self.central_layout.addSpacing(20)

        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 800, 20))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def select_folder(self):
        self.set_select_volume_btns(True)
        self.folder_path = QtWidgets.QFileDialog.getExistingDirectory(
            self.central_widget, "Select manga folder", ""
        )
        if self.folder_path != "":
            self.vc_paths = []
            try:
                self.vc = VolumeCollection()
                for p in Path(self.folder_path).expanduser().absolute().iterdir():
                    if (p.is_dir() and p.stem != "_ocr") or (
                            p.is_file() and p.suffix.lower() in {".zip", ".cbz"}
                    ):
                        self.vc.add_path_in(p)
                        self.vc_paths.append(p)
            except Exception as e:
                self.show_error_msg(f"Error while scanning paths: {e}")
                self.set_select_volume_btns(False)
                return
            self.process_volumes()
        else:
            self.set_select_volume_btns(False)

    def select_files(self):
        self.set_select_volume_btns(True)
        options = QtWidgets.QFileDialog.Options()
        file_filter = "Zip Files (*.zip);;CBZ Files (*.cbz);;All Files (*.*)"
        initial_filter = "CBZ Files (*.cbz)"
        self.file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self.central_widget, "Select manga files", "", file_filter, initial_filter, options)

        if len(self.file_paths) > 0:
            self.vc_paths = []
            try:
                self.vc = VolumeCollection()
                for file in self.file_paths:
                    p = Path(file)
                    self.vc.add_path_in(p)
                    self.vc_paths.append(p)
            except Exception as e:
                self.show_error_msg(f"Error while scanning paths: {e}")
                self.set_select_volume_btns(False)
                return
            self.process_volumes()
        else:
            self.set_select_volume_btns(False)

    def process_volumes(self):
        if len(self.vc) == 0:
            self.show_error_msg("Found no paths to process. Did you set the paths correctly?")
            self.set_select_volume_btns(False)
            return

        try:
            for title in self.vc.titles.values():
                title.set_uuid()
        except Exception as e:
            self.show_error_msg(f"Error while scanning titles: {e}")
            self.set_select_volume_btns(False)
            return

        self.show_summary_volume_collection()

    def show_summary_volume_collection(self):
        layout = QtWidgets.QVBoxLayout()
        self.number_of_selected_volumes = len(self.vc)
        self.number_of_volumes_label = QtWidgets.QLabel(f"Selected volumes: {len(self.vc)}/{self.number_of_selected_volumes}")
        layout.addWidget(self.number_of_volumes_label)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setMinimumSize(700, 250)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        checkbox_container = QtWidgets.QFrame()
        checkbox_layout = QtWidgets.QVBoxLayout(checkbox_container)

        self.volumes_checkboxes = []

        self.uncheck_all_checkboxes = True
        self.select_all_checkboxes = QtWidgets.QCheckBox("Select all volumes")
        self.select_all_checkboxes.setChecked(True)
        self.select_all_checkboxes.stateChanged.connect(self.select_all_volumes_checkboxes)
        checkbox_layout.addWidget(self.select_all_checkboxes)

        self.uncheck_unprocessed_volumes = True
        self.select_unprocessed_checkboxes = QtWidgets.QCheckBox("Select only unprocessed volumes")
        self.select_unprocessed_checkboxes.setChecked(False)
        self.select_unprocessed_checkboxes.stateChanged.connect(self.select_unprocessed_volumes_checkboxes)
        checkbox_layout.addWidget(self.select_unprocessed_checkboxes)
        for volume in self.vc:
            checkbox = QtWidgets.QCheckBox(str(volume))
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.update_number_of_selected_volumes_label)
            self.volumes_checkboxes.append(checkbox)
            checkbox_layout.addWidget(checkbox)

        checkbox_container.setLayout(checkbox_layout)
        scroll_area.setWidget(checkbox_container)
        layout.addWidget(scroll_area)

        button_layout = QHBoxLayout()
        continue_btn = QtWidgets.QPushButton("Start")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        button_layout.addWidget(continue_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.summary_volume_collection_win = QtWidgets.QDialog()
        self.summary_volume_collection_win.setLayout(layout)
        self.summary_volume_collection_win.setWindowTitle("Volume Collection")
        self.summary_volume_collection_win.adjustSize()
        self.summary_volume_collection_win.setFixedSize(750, 350)
        self.summary_volume_collection_win.finished.connect(lambda: self.set_select_volume_btns(False))

        continue_btn.clicked.connect(lambda: self.execute_mokuro())
        cancel_btn.clicked.connect(lambda: self.summary_volume_collection_win.close())

        self.summary_volume_collection_win.exec_()

    def set_select_volume_btns(self, state):
        self.show_select_folder_btn.setDisabled(state)
        self.show_select_files_btn.setDisabled(state)

    def select_all_volumes_checkboxes(self, state):
        if state == 2:
            for checkbox in self.volumes_checkboxes:
                checkbox.setChecked(True)
        if state == 0:
            if self.uncheck_all_checkboxes:
                for checkbox in self.volumes_checkboxes:
                    checkbox.setChecked(False)
                self.uncheck_all_checkboxes = True
            else:
                self.uncheck_all_checkboxes = True

    def select_unprocessed_volumes_checkboxes(self, state):
        if state == 2:
            for checkbox in self.volumes_checkboxes:
                if "unprocessed" in checkbox.text() or "partially processed" in checkbox.text():
                    checkbox.setChecked(True)
                else:
                    checkbox.setChecked(False)
            self.uncheck_all_checkboxes = True
            self.check_all_volumes_checked()
        if state == 0:
            if self.uncheck_unprocessed_volumes:
                for checkbox in self.volumes_checkboxes:
                    if "unprocessed" in checkbox.text() or "partially processed" in checkbox.text():
                        checkbox.setChecked(False)
            self.uncheck_unprocessed_volumes = True
            self.uncheck_all_checkboxes = True

    def update_number_of_selected_volumes_label(self, state):
        if state == 2:
            self.number_of_selected_volumes += 1
            self.check_all_volumes_checked()
        if state == 0:
            self.number_of_selected_volumes -= 1
            self.uncheck_all_checkboxes = False
            self.select_all_checkboxes.setChecked(False)
        self.number_of_volumes_label.setText(f"Selected volumes: {self.number_of_selected_volumes}/{len(self.vc)}")
        self.check_all_unprocessed_checked()

    def check_all_volumes_checked(self):
        if len(self.vc) == self.number_of_selected_volumes:
            self.select_all_checkboxes.setChecked(True)

    def check_all_unprocessed_checked(self):
        all_checked = True
        for checkbox in self.volumes_checkboxes:
            if "unprocessed" in checkbox.text() or "partially processed" in checkbox.text():
                if not checkbox.isChecked():
                    all_checked = False
                    break
            else:
                if checkbox.isChecked():
                    all_checked = False
                    break

        if all_checked:
            self.select_unprocessed_checkboxes.setChecked(True)
        else:
            self.uncheck_unprocessed_volumes = False
            self.select_unprocessed_checkboxes.setChecked(False)

    def get_selected_volumes(self):
        vc = VolumeCollection()
        try:
            for i, cb in enumerate(self.volumes_checkboxes):
                if cb.isChecked():
                    vc.add_path_in(self.vc_paths[i])
        except Exception as e:
            self.show_error_msg(f"Error while scanning volumes: {e}")

        return vc

    def execute_mokuro(self):
        selected_volumes = self.get_selected_volumes()

        if len(selected_volumes) == 0:
            self.show_error_msg("No selected volumes.")
            self.set_select_volume_btns(False)
            return

        self.summary_volume_collection_win.close()
        self.set_select_volume_btns(True)
        self.volumes_processed = 0
        self.per_volume_percentage = 100 / len(selected_volumes)

        if hasattr(self, "current_processing_volume_label"):
            self.central_layout.removeWidget(self.current_processing_volume_label)
            self.current_processing_volume_label.deleteLater()

        if hasattr(self, "progress_bar"):
            self.central_layout.removeWidget(self.progress_bar)
            self.progress_bar.deleteLater()

        if hasattr(self, "command_output"):
            self.central_layout.removeWidget(self.command_output)
            self.command_output.deleteLater()

        self.current_processing_volume_label = QtWidgets.QLabel()
        self.central_layout.addWidget(self.current_processing_volume_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.central_layout.addWidget(self.progress_bar)

        self.command_output = QtWidgets.QTextEdit(self.central_widget)
        self.command_output.setReadOnly(True)
        self.central_layout.addWidget(self.command_output)
        self.command_output.append("Initiating mokuro...\n\n\n")

        self.worker_thread = WorkerThread(selected_volumes)
        self.worker_thread.start()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.process_queues)
        self.timer.start(50)

    def process_queues(self):
        while not update_command_output.empty():
            self.command_output.append(update_command_output.get())
            self.scroll_command_output()

        while not update_current_volume.empty():
            self.current_processing_volume_label.setText(update_current_volume.get())
            self.progress_bar.setValue(
                int(self.volumes_processed * self.per_volume_percentage)
            )
            self.volumes_processed += 1

        while not finished_processing.empty():
            self.timer.stop()
            message = finished_processing.get()
            self.command_output.append(f"\n\n\n{message}\n\n\n")
            self.scroll_command_output()
            self.progress_bar.setValue(100)

            self.set_select_volume_btns(False)

            message_box = QtWidgets.QMessageBox()
            message_box.setWindowTitle("Finished")
            message_box.setIcon(QtWidgets.QMessageBox.Information)
            message_box.setText(message)
            message_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
            message_box.exec_()

    def scroll_command_output(self):
        cursor = self.command_output.textCursor()
        cursor.movePosition(cursor.End)
        self.command_output.setTextCursor(cursor)
        self.command_output.ensureCursorVisible()

    def write(self, message):
        update_command_output.put(message)

    def flush(self):
        pass

    def show_error_msg(self, message):
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("Error")
        msg.setText(message)
        msg.exec_()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon("assets/icon.ico"))
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    sys.stdout = ui
    sys.stderr = ui
    logger.remove()
    logger.add(ui, level="INFO")
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())
