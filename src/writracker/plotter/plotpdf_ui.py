import sys
import os
import subprocess
import traceback
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QListWidget, QPushButton, QFileDialog, QAbstractItemView,
                             QLabel, QLineEdit, QMessageBox, QProgressBar, QTextEdit)
from PyQt5.QtCore import QThread, QObject, pyqtSignal

import writracker.plotter.plotpdf as ppdf


#==================================================================================================
def run():
    app = QApplication(sys.argv)
    dialog = SelectFilesDialog()
    dialog.show()
    sys.exit(app.exec_())


#==================================================================================================
class SelectFilesDialog(QDialog):
    """
    First dialog: select input and output directories
    """

    #--------------------------------------------------------------------------
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WriTracker: pdf Plotter")

        main_layout = QVBoxLayout(self)

        label_above = QLabel("Choose WEncoder output directories to plot from")
        main_layout.addWidget(label_above)

        mid_layout = QHBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.addItems([])
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        mid_layout.addWidget(self.list_widget, 1)

        btn_layout = QVBoxLayout()
        self.btn_add = QPushButton('+')
        self.btn_add_subfolders = QPushButton('++')
        self.btn_remove = QPushButton('-')
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_add_subfolders)
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addStretch()
        mid_layout.addLayout(btn_layout)

        main_layout.addLayout(mid_layout)

        output_layout = QHBoxLayout()
        label_output = QLabel("Output directory:")
        output_layout.addWidget(label_output)

        self.output_lineedit = QLineEdit()
        self.output_lineedit.setReadOnly(True)  # User selects directory, no typing
        output_layout.addWidget(self.output_lineedit)

        self.btn_output_file = QPushButton("...")
        self.btn_output_file.setFixedWidth(40)
        output_layout.addWidget(self.btn_output_file)

        main_layout.addLayout(output_layout)

        self.btn_prepare_pdf = QPushButton("Prepare pdf!")
        self.btn_prepare_pdf.setEnabled(False)
        main_layout.addWidget(self.btn_prepare_pdf)

        self.init_button_operations()

        self.generating = False

    #--------------------------------------------------------------------------
    def closeEvent(self, event):
        super().closeEvent(event)
        if not self.generating:
            QApplication.instance().quit()

    #--------------------------------------------------------------------------
    # noinspection PyUnresolvedReferences
    def init_button_operations(self):
        self.btn_add.clicked.connect(self.add_one_input_dir)
        self.btn_add_subfolders.clicked.connect(self.add_input_subfolders)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_output_file.clicked.connect(self.select_output_directory)
        self.list_widget.itemSelectionChanged.connect(self.update_prepare_button)
        self.output_lineedit.textChanged.connect(self.update_prepare_button)
        self.btn_prepare_pdf.clicked.connect(self.prepare_pdf)

    #--------------------------------------------------------------------------
    def remove_selected(self):
        for item in reversed(self.list_widget.selectedItems()):
            self.list_widget.takeItem(self.list_widget.row(item))
        self.update_prepare_button()

    #--------------------------------------------------------------------------
    def add_one_input_dir(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select a folder with the encoded data')
        if folder is not None and folder != '':
            self.update_input_dirs([folder])

    #--------------------------------------------------------------------------
    def add_input_subfolders(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select a folder that contains several encoded datasets (each in a separate subfolder)')
        if folder is not None and folder != '':
            try:
                subfolders = [os.path.join(folder, name) for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name))]
                self.update_input_dirs(subfolders)
            except Exception as e:
                print(f"Error listing subfolders: {e}")

    #--------------------------------------------------------------------------
    def update_input_dirs(self, add_dirs):
        items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        items.extend(add_dirs)
        items = sorted(set(items))  # Remove duplicates and sort
        self.list_widget.clear()
        self.list_widget.addItems(items)
        self.update_prepare_button()

    #--------------------------------------------------------------------------
    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_lineedit.setText(directory)
            self.update_prepare_button()

    #--------------------------------------------------------------------------
    def update_prepare_button(self):
        list_not_empty = self.list_widget.count() > 0
        directory_not_empty = bool(self.output_lineedit.text().strip())
        self.btn_prepare_pdf.setEnabled(list_not_empty and directory_not_empty)

    #--------------------------------------------------------------------------
    def prepare_pdf(self):
        output_dir = os.path.abspath(self.output_lineedit.text().strip())
        if not output_dir:
            QMessageBox.critical(self, "Error", "Output directory cannot be empty.")
            return

        if not os.path.isdir(output_dir):
            create = QMessageBox.question(self, 'Directory does not exist',
                                          f'The directory {output_dir} does not exist.\nDo you want to create it?',
                                          QMessageBox.Yes | QMessageBox.No)
            if create == QMessageBox.Yes:
                try:
                    os.makedirs(output_dir)
                except Exception as e:
                    QMessageBox.critical(self, 'Error', f'Failed to create directory: \n{e}')
                    return
            else:
                return

        input_dirs = [os.path.abspath(self.list_widget.item(i).text()) for i in range(self.list_widget.count())]
        conflicting_files = []
        for orig_dir in input_dirs:
            base_name = os.path.basename(orig_dir)
            candidate_file = os.path.join(output_dir, f"{base_name}.pdf")
            if os.path.isfile(candidate_file):
                conflicting_files.append(f"{base_name}.pdf")

        if conflicting_files:
            dir_name = os.path.basename(output_dir.rstrip(os.sep)) or output_dir
            files_list = ", ".join(conflicting_files)
            result = QMessageBox.question(
                self, "Overwrite confirmation",
                f"The following files exist in '{dir_name}' and will be overridden: \n{files_list}\nAre you sure?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result != QMessageBox.Yes:
                return

        self.generating = True
        self.close()
        progress_dialog = PreparePdfProgressDialog(input_dirs, output_dir)
        progress_dialog.start_plotting()
        progress_dialog.exec_()


#==================================================================================================
# noinspection PyAttributeOutsideInit
class PreparePdfProgressDialog(QDialog):
    """
    Execute the plotting process
    """

    #--------------------------------------------------------------------------
    def __init__(self, input_dirs, target_dir):
        super().__init__()
        self.setWindowTitle("WriTracker: pdf Plotter")
        self.target_dir = target_dir
        self.input_dirs = input_dirs

        self.resize(500, 350)

        layout = QVBoxLayout(self)
        self.top_label = QLabel("")
        layout.addWidget(self.top_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.message_box = QTextEdit()
        self.message_box.setReadOnly(True)
        self.message_box.setLineWrapMode(QTextEdit.NoWrap)
        self.message_box.setFixedHeight(self.message_box.fontMetrics().lineSpacing() * 12)
        layout.addWidget(self.message_box)

        button_layout = QHBoxLayout()
        self.btn_reveal = QPushButton("preparing...")
        self.btn_reveal.setEnabled(False)
        button_layout.addWidget(self.btn_reveal)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(True)
        button_layout.addWidget(self.btn_cancel)
        layout.addLayout(button_layout)

        # noinspection PyUnresolvedReferences
        self.btn_reveal.clicked.connect(self.reveal_in_finder)
        # noinspection PyUnresolvedReferences
        self.btn_cancel.clicked.connect(self.cancel_clicked)

    def closeEvent(self, event):
        super().closeEvent(event)
        QApplication.instance().quit()

    #--------------------------------------------------------------------------
    def on_dataset_started(self, ds_num, ds_name):
        self.top_label.setText(f"Processing dataset {ds_num}/{len(self.input_dirs)} ({ds_name})")
        self.progress_bar.setValue(0)

    #--------------------------------------------------------------------------
    def on_dataset_finished(self, msg):
        self.message_box.append(msg)
        self.progress_bar.setValue(100)

    #--------------------------------------------------------------------------
    def on_progress(self, pcnt):
        self.progress_bar.setValue(pcnt)

    #--------------------------------------------------------------------------
    def on_finished_all(self):
        self.top_label.setText("Preparation complete")
        self.btn_cancel.setEnabled(False)
        self.btn_reveal.setText("reveal in finder")
        self.btn_reveal.setEnabled(True)

    #--------------------------------------------------------------------------
    def start_plotting(self):
        self.plotter = MultiPlotter(self.input_dirs, self.target_dir, config=ppdf.PdfPlotterConfig(),
                                    signaller=Signaller().connect_signals(self))
        self.runner = PlotRunner(self.plotter, self)
        self.runner.start()

    #--------------------------------------------------------------------------
    def cancel_clicked(self):
        if not hasattr(self, 'plotter') or self.plotter is None:
            return

        self.btn_cancel.setEnabled(False)
        self.plotter.stop()
        self.top_label.setText("Operation cancelled")

    #--------------------------------------------------------------------------
    def reveal_in_finder(self):
        if os.path.exists(self.target_dir):
            try:
                fn1 = self.target_dir + os.sep + os.path.basename(self.input_dirs[0]) + ".pdf"
                subprocess.run(["open", "-R", fn1])
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open in Finder: \n{e}")
        else:
            QMessageBox.warning(self, "File not found", "The output file does not exist.")


#==================================================================================================
class PlotRunner(QThread):

    def __init__(self, plotter, ui):
        super().__init__()
        self.plotter = plotter
        self.signaller = Signaller().connect_signals(ui)

    def run(self):
        QThread.msleep(200)  # Give the UI time to update
        self.plotter.plot()


#==================================================================================================
class Signaller(QObject):
    """
    As the pdf-generation is going on, we send signals from this thread to the UI in order to update the UI accordingly.
    This object mediates the signal-sending
    """

    ds_started = pyqtSignal(int, str)  # send progress percent
    ds_finished = pyqtSignal(str)  # send progress percent
    all_finished = pyqtSignal()  # send progress percent
    progress_changed = pyqtSignal(int)  # send progress percent

    # noinspection PyUnresolvedReferences
    def connect_signals(self, ui):
        self.ds_started.connect(ui.on_dataset_started)
        self.ds_finished.connect(ui.on_dataset_finished)
        self.progress_changed.connect(ui.on_progress)
        self.all_finished.connect(ui.on_finished_all)
        return self


#==================================================================================================
class MultiPlotter(ppdf.MultiFilePdfPlotter):

    def __init__(self, input_dirs, target_dir, config, signaller=None):
        super().__init__(input_dirs, target_dir, config=config)
        self.signaller = signaller

    def create_one_file_plotter(self, ds_dir_name, out_fn, config):
        return Plotter(ds_dir_name, out_fn, config, self.signaller)

    def plot(self):
        super().plot()
        self.signaller.all_finished.emit()

    def on_ds_started(self, ds_num, ds_dir):
        self.signaller.ds_started.emit(ds_num+1, os.path.basename(ds_dir))
        QThread.yieldCurrentThread()

    def on_ds_finished(self, ds_num, ds_dir):
        ds_name = os.path.basename(ds_dir)
        self.signaller.ds_finished.emit(f"Finished processing dataset #{ds_num+1}: {ds_name}")
        QThread.yieldCurrentThread()

    def on_exception(self, ds_num, ds_dir, exc):
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        ds_name = os.path.basename(ds_dir)
        self.signaller.ds_finished.emit(f"Error in dataset #{ds_num+1} ({ds_name}): {exc}")
        QThread.yieldCurrentThread()


#==================================================================================================
class Plotter(ppdf.OneFilePdfPlotter):

    def __init__(self, ds_dir_name, out_fn, config, signaller):
        super().__init__(input=ds_dir_name, out_fn=out_fn, config=config)
        self.signaller = signaller

    def init_progress_bar(self):
        pass

    def update_progress_bar(self, n_done):
        print(f'Finished {n_done} trials')
        percent = int((n_done / len(self.trials)) * 100)
        self.signaller.progress_changed.emit(percent)
        QThread.yieldCurrentThread()
