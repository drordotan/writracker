import sys
import os
import subprocess
import traceback
import warnings
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QListWidget, QPushButton, QFileDialog, QAbstractItemView,
                             QLabel, QLineEdit, QMessageBox, QProgressBar, QTextEdit,
                             QGroupBox, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox, QWidget)
from PyQt5.QtCore import QThread, QObject, pyqtSignal, Qt

import writracker.plotter.pdfplotter as ppdf
import writracker.utils as wu
import writracker.uiutils as uiu


warnings.filterwarnings("ignore", message="Starting a Matplotlib GUI outside of the main thread will likely fail.")


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
        self.btn_add.setToolTip('Add a single input folder')
        self.btn_add_subfolders = QPushButton('++')
        self.btn_add_subfolders.setToolTip('Add all child folders of the selected folder')
        self.btn_add_recursively = QPushButton('+++')
        self.btn_add_recursively.setToolTip('Add any descendent folder that contains a "trials.csv" file')
        self.btn_remove = QPushButton('-')
        self.btn_remove.setToolTip('Remove the selected folders')

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_add_subfolders)
        btn_layout.addWidget(self.btn_add_recursively)
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

        # ---------------- Parameters (Dialog #1) ----------------
        params_group = QGroupBox("")
        params_vbox = QVBoxLayout(params_group)
        params_vbox.setSpacing(6)

        def hline():
            line = QWidget()
            line.setFixedHeight(1)
            line.setStyleSheet("background-color: #C0C0C0;")
            return line

        # Small helpers (like the other app)
        def help_link(text):
            link = QLabel("<a href='#'>?</a>")
            link.setToolTip(text)
            link.setTextFormat(Qt.RichText)
            link.setOpenExternalLinks(False)
            link.setFixedWidth(16)
            def _click():
                QMessageBox.information(self, "Help", text)
            link.linkActivated.connect(lambda _: _click())
            return link

        def row_with_help(widget, helptext):
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(widget, 1)
            h.addWidget(help_link(helptext), 0)
            return w

        # --- Contents section ---
        params_vbox.addWidget(hline())
        params_vbox.addWidget(QLabel("<b>Information to show</b>"))
        contents_form = QFormLayout()
        contents_form.setHorizontalSpacing(12)
        contents_form.setVerticalSpacing(6)

        # 1) Bounding box (Yes/No) + percentages for X/Y to the right
        self.combo_bounding_box = QComboBox()
        self.combo_bounding_box.addItems(["No", "Yes"])
        help_bb = ("Display each character's bounding box. "
                   "You can specify the fraction of pixels that would fit in the bounding box, separately for the x/y axes (100% = all pixels)")
        bb_row_widget = QWidget()
        bb_row = QHBoxLayout(bb_row_widget)
        bb_row.setContentsMargins(0, 0, 0, 0)
        bb_row.addWidget(self.combo_bounding_box)
        bb_row.addSpacing(12)
        lbl_pct = QLabel("% of pixels in the b.box:")
        lbl_pct.setToolTip(help_bb)
        bb_row.addWidget(lbl_pct)
        self.spin_frac_x = QDoubleSpinBox()
        self.spin_frac_x.setRange(0.0, 100.0)
        self.spin_frac_x.setSingleStep(1.0)
        self.spin_frac_x.setValue(100)
        self.spin_frac_x.setSuffix("% X")
        self.spin_frac_x.setToolTip(help_bb)
        self.spin_frac_y = QDoubleSpinBox()
        self.spin_frac_y.setRange(0.0, 100.0)
        self.spin_frac_y.setSingleStep(1.0)
        self.spin_frac_y.setValue(100)
        self.spin_frac_y.setSuffix("% Y")
        self.spin_frac_y.setToolTip(help_bb)
        bb_row.addWidget(self.spin_frac_x)
        bb_row.addWidget(self.spin_frac_y)
        bb_row.addStretch()
        contents_form.addRow(QLabel("Character bounding box"), row_with_help(bb_row_widget, help_bb))

        # 2) Character order (Yes/No)
        self.combo_char_order = QComboBox()
        self.combo_char_order.addItems(["No", "Yes"])
        help_order = "Overlay an index showing the order in which the participant wrote each character."
        contents_form.addRow(QLabel("Character writing order"), row_with_help(self.combo_char_order, help_order))

        # 3) Temporal gaps (Yes/No)
        self.combo_temporal_gaps = QComboBox()
        self.combo_temporal_gaps.addItems(["No", "Yes"])
        help_gaps = "Display the inter-character temporal gaps on the page."
        contents_form.addRow(QLabel("Inter-character temporal gaps"), row_with_help(self.combo_temporal_gaps, help_gaps))

        # 4) Trial title — identical style to the other app (line edit + '?' help; preview button removed)
        ttip_trial_title = ('The title to show on each trial (empty = no title). You can use {keyword} for trial-specific values')
        help_trial_title = ('The title to show on each trial (empty = no title). You can use {keyword} with any of these:\n' +
                            '{target} - The ID/number of the target stimulus\n' +
                            '{trial_id} - The trial number (two attempts = two separate IDs)\n' +
                            '{block} - Block number in the experiment\n' +
                            '{stimulus} - The target shown\n' +
                            '{response} - What the participant wrote, "=" for correct\n' +
                            '{rc} - "OK" or the error code\n' +
                            '{nchars} - Number of response characters\n' +
                            '{nstrokes} - Number of response strokes')
        title_row_widget = QWidget()
        title_row = QHBoxLayout(title_row_widget)
        title_row.setContentsMargins(0, 0, 0, 0)
        self.title_lineedit = QLineEdit()
        self.title_lineedit.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.title_lineedit.setPlaceholderText("Enter title or use {keywords}")
        self.title_lineedit.setToolTip(ttip_trial_title)
        self.title_lineedit.setMinimumWidth(600)
        self.title_lineedit.setText("Trial #{trial_id}")
        title_row.addWidget(self.title_lineedit)
        title_row.addWidget(help_link(help_trial_title))
        contents_form.addRow(QLabel("Trial title"), title_row_widget)

        params_vbox.addLayout(contents_form)

        # --- Page looks section ---
        params_vbox.addWidget(hline())
        params_vbox.addWidget(QLabel("<b>Page looks</b>"))
        looks_form = QFormLayout()
        looks_form.setHorizontalSpacing(12)
        looks_form.setVerticalSpacing(6)

        # Dot size
        self.spin_dot_size = QDoubleSpinBox()
        self.spin_dot_size.setRange(1.0, 10.0)
        self.spin_dot_size.setSingleStep(0.5)
        self.spin_dot_size.setValue(2.0)
        help_dot = "Size of the plotted points on the page."
        looks_form.addRow(QLabel("Dot size"), row_with_help(self.spin_dot_size, help_dot))

        # Number of columns
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 3)
        self.spin_cols.setValue(2)
        help_cols = "Number of columns (pages are laid out as a grid of rows × columns)."
        looks_form.addRow(QLabel("Number of columns"), row_with_help(self.spin_cols, help_cols))

        # Number of rows
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 10)
        self.spin_rows.setValue(5)
        help_rows = "Number of rows (pages are laid out as a grid of rows × columns)."
        looks_form.addRow(QLabel("Number of rows"), row_with_help(self.spin_rows, help_rows))

        params_vbox.addLayout(looks_form)
        main_layout.addWidget(params_group)

        # Prepare button
        self.btn_prepare_pdf = QPushButton("Prepare pdf!")
        self.btn_prepare_pdf.setEnabled(False)
        main_layout.addWidget(self.btn_prepare_pdf)

        uiu.add_copyright_msg(main_layout, 2025, 'Dror Dotan')

        self.init_button_operations()
        # Enable/disable fraction fields depending on bounding-box toggle
        self.combo_bounding_box.currentIndexChanged.connect(self.update_fraction_enabled)
        self.update_fraction_enabled()

        self.generating = False

    #--------------------------------------------------------------------------
    def closeEvent(self, event):
        super().closeEvent(event)
        if not self.generating:
            QApplication.instance().quit()

    #--------------------------------------------------------------------------
    # noinspection PyUnresolvedReferences
    def init_button_operations(self):
        self.btn_add.clicked.connect(self.on_clicked_add_one_input_dir)
        self.btn_add_subfolders.clicked.connect(self.on_clicked_add_input_subfolders)
        self.btn_add_recursively.clicked.connect(self.on_clicked_add_recursively)
        self.btn_remove.clicked.connect(self.on_clicked_remove_selected)
        self.btn_output_file.clicked.connect(self.on_clicked_select_output_directory)
        self.list_widget.itemSelectionChanged.connect(self.update_prepare_button)
        self.output_lineedit.textChanged.connect(self.update_prepare_button)
        self.btn_prepare_pdf.clicked.connect(self.on_clicked_prepare_pdf)

    #--------------------------------------------------------------------------
    def update_fraction_enabled(self):
        enable = (self.combo_bounding_box.currentText() == "Yes")
        self.spin_frac_x.setEnabled(enable)
        self.spin_frac_y.setEnabled(enable)

    #--------------------------------------------------------------------------
    def on_clicked_remove_selected(self):
        for item in reversed(self.list_widget.selectedItems()):
            self.list_widget.takeItem(self.list_widget.row(item))
        self.update_prepare_button()

    #--------------------------------------------------------------------------
    def on_clicked_add_one_input_dir(self):
        folder = self.select_folder('Select a folder with the encoded data')
        if folder is None:
            return

        self.add_selected_input_dirs([folder])

    #--------------------------------------------------------------------------
    def on_clicked_add_input_subfolders(self):
        folder = self.select_folder('Select a folder that contains several encoded datasets (each in a separate subfolder)')
        if folder is None:
            return

        subfolders = self.get_descendent_folders(folder)
        self.add_selected_input_dirs(subfolders)

    #--------------------------------------------------------------------------
    def on_clicked_add_recursively(self):
        folder = self.select_folder('Select a folder. All descendent folders will be added')
        if folder is None:
            return

        subfolders = self.get_descendent_folders(folder, recursive=True)
        self.add_selected_input_dirs(subfolders)

    #--------------------------------------------------------------------------
    def get_descendent_folders(self, folder, recursive=False, only_relevant=True):
        children = [os.path.join(folder, name) for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name))]
        grandchildren = []
        if recursive:
            for child in list(children):
                grandchildren.extend(self.get_descendent_folders(child, recursive=True, only_relevant=only_relevant))

        if only_relevant:
            children = [c for c in children if os.path.isfile(os.path.join(c, 'trials.csv'))]

        children.extend(grandchildren)

        return children

    #--------------------------------------------------------------------------
    def select_folder(self, msg):
        if not wu.is_windows():
            QMessageBox.information(None, 'Select folder', msg)
        folder = QFileDialog.getExistingDirectory(self, msg)
        return None if folder == '' else folder

    #--------------------------------------------------------------------------
    def add_selected_input_dirs(self, add_dirs):
        items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        items.extend(add_dirs)
        items = sorted(set(items))  # Remove duplicates and sort
        self.list_widget.clear()
        self.list_widget.addItems(items)
        self.update_prepare_button()

    #--------------------------------------------------------------------------
    def on_clicked_select_output_directory(self):
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
    def on_clicked_prepare_pdf(self):
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

        # ------ collect parameters -> PdfPlotterConfig ------
        bounding_box = (self.combo_bounding_box.currentText() == "Yes")
        char_order = (self.combo_char_order.currentText() == "Yes")
        temporal_gaps = (self.combo_temporal_gaps.currentText() == "Yes")
        # Convert percent spinners to fractions in [0,1]
        fx = self.spin_frac_x.value() / 100.0 if bounding_box else None
        fy = self.spin_frac_y.value() / 100.0 if bounding_box else None
        cols = self.spin_cols.value()
        rows = self.spin_rows.value()
        dot_size = float(self.spin_dot_size.value())
        title_txt = self.title_lineedit.text().strip() or None

        # --- VALIDATE title keywords against ppdf.TrialTitle().keywords ---
        if title_txt:
            import re
            requested = set(re.findall(r"\{(\w+)\}", title_txt))
            allowed = set(ppdf.TrialTitle().keywords)
            invalid = sorted(requested - allowed)
            if invalid:
                msg = 'Unknown keyword(s) in "Trial Title" definition: {}\n'.format(", ".join(invalid)) + \
                      'Allowed keywords are: {}'.format(", ".join(sorted(allowed)))
                QMessageBox.critical(self, 'Invalid keyword in trial title', msg)
                return

        cfg = ppdf.PdfPlotterConfig(
            bounding_box=bounding_box,
            char_order=char_order,
            temporal_gaps=temporal_gaps,
            fraction_of_x_points=fx,
            fraction_of_y_points=fy,
            cols_per_page=cols,
            rows_per_page=rows,
            trial_title=ppdf.TrialTitle(title=title_txt),
            dot_size=dot_size
        )

        self.generating = True
        self.close()
        progress_dialog = PreparePdfProgressDialog(input_dirs, output_dir, cfg)
        progress_dialog.start_plotting()
        progress_dialog.exec_()


#==================================================================================================
# noinspection PyAttributeOutsideInit
class PreparePdfProgressDialog(QDialog):
    """
    Execute the plotting process
    """

    #--------------------------------------------------------------------------
    def __init__(self, input_dirs, target_dir, config):
        super().__init__()
        self.setWindowTitle("WriTracker: pdf Plotter")
        self.target_dir = target_dir
        self.input_dirs = input_dirs
        self.config = config

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

        uiu.add_copyright_msg(layout, 2025, 'Dror Dotan')

        # noinspection PyUnresolvedReferences
        self.btn_reveal.clicked.connect(self.reveal_in_finder)
        # noinspection PyUnresolvedReferences
        self.btn_cancel.clicked.connect(self.on_clicked_cancel)

        self.n_done = 0
        self.n_succeeded = 0
        self.canceled = False

    def closeEvent(self, event):
        super().closeEvent(event)
        QApplication.instance().quit()

    #--------------------------------------------------------------------------
    def on_dataset_started(self, ds_num, ds_name):
        self.top_label.setText(f"Processing dataset {ds_num}/{len(self.input_dirs)} ({ds_name})")
        self.progress_bar.setValue(0)

    #--------------------------------------------------------------------------
    def on_dataset_finished(self, ds_num, succeeded, msg):
        self.n_done = ds_num + 1
        self.n_succeeded += int(succeeded)
        self.message_box.append(msg)
        self.progress_bar.setValue(100)

    #--------------------------------------------------------------------------
    def on_progress(self, pcnt):
        self.progress_bar.setValue(pcnt)

    #--------------------------------------------------------------------------
    def on_finished_all(self):
        n_datasets = len(self.input_dirs)
        if self.canceled:
            self.top_label.setText(f'Canceled; still, created PDFs for {self.n_succeeded}/{n_datasets} datasets')
        else:
            self.top_label.setText(f'Finished creating PDFs for {self.n_succeeded}/{n_datasets} datasets')

        self.btn_cancel.setEnabled(False)
        self.btn_reveal.setText("reveal in finder")
        self.btn_reveal.setEnabled(True)

    #--------------------------------------------------------------------------
    def start_plotting(self):
        self.plotter = MultiPlotter(self.input_dirs, self.target_dir, config=self.config,
                                    signaller=Signaller().connect_signals(self))
        self.runner = PlotRunner(self.plotter, self)
        self.runner.start()

    #--------------------------------------------------------------------------
    def on_clicked_cancel(self):
        if not hasattr(self, 'plotter') or self.plotter is None:
            return

        self.canceled = True
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
    ds_finished = pyqtSignal(int, bool, str)  # send progress percent
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
        self.signaller.ds_finished.emit(ds_num, True, f"Finished processing dataset #{ds_num+1}: {ds_name}")
        QThread.yieldCurrentThread()

    def on_exception(self, ds_num, ds_dir, exc):
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        ds_name = os.path.basename(ds_dir)
        self.signaller.ds_finished.emit(ds_num, False, f"Error in dataset #{ds_num+1} ({ds_name}): {exc}")
        QThread.yieldCurrentThread()


#==================================================================================================
class Plotter(ppdf.OneFilePdfPlotter):

    def __init__(self, ds_dir_name, out_fn, config, signaller):
        super().__init__(ds_spec=ds_dir_name, out_fn=out_fn, config=config)
        self.signaller = signaller

    def init_progress_bar(self):
        pass

    def update_progress_bar(self, n_done):
        percent = int((n_done / len(self.trials)) * 100)
        self.signaller.progress_changed.emit(percent)
        QThread.yieldCurrentThread()
