import sys
import os
import subprocess
import traceback
import csv
import re
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QFileDialog, QAbstractItemView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QEvent

from writracker.plotter.mplotter import MoviePlotter
import writracker.uiutils as uiu


#---------------------------------------------------------------------------------------------------
def run():
    app = QApplication(sys.argv)
    dialog = SelectFilesDialog()
    dialog.show()
    sys.exit(app.exec_())


#---------------------------------------------------------------------------------------------------
class SelectFilesDialog(QDialog):

    #-----------------------------------------------------------------
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Writracker: Movie plotter")
        self.resize(900, 600)

        main_layout = QVBoxLayout(self)

        label_above = QLabel("Select trajectory files to plot")
        main_layout.addWidget(label_above)

        # --- File list + buttons ---
        mid_layout = QHBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setMinimumWidth(550)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        mid_layout.addWidget(self.list_widget, 1)

        btn_layout = QVBoxLayout()
        self.btn_add = QPushButton("+")
        self.btn_add.setToolTip("Add one or more CSV files")
        self.btn_remove = QPushButton("-")
        self.btn_remove.setToolTip("Remove selected file(s)")
        self.btn_up = QPushButton("↑")
        self.btn_up.setToolTip("Move up")
        self.btn_down = QPushButton("↓")
        self.btn_down.setToolTip("Move down")

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addWidget(self.btn_up)
        btn_layout.addWidget(self.btn_down)
        btn_layout.addStretch()
        mid_layout.addLayout(btn_layout)
        main_layout.addLayout(mid_layout)

        # --- Output file ---
        output_layout = QHBoxLayout()
        label_output = QLabel("Output movie file:")
        output_layout.addWidget(label_output)
        self.output_lineedit = QLineEdit()
        self.output_lineedit.setReadOnly(True)
        self.output_lineedit.setToolTip("Where to save the generated .mp4 file")
        output_layout.addWidget(self.output_lineedit)
        self.btn_output_file = QPushButton("…")
        self.btn_output_file.setFixedWidth(40)
        self.btn_output_file.setToolTip("Choose output .mp4 file")
        output_layout.addWidget(self.btn_output_file)
        main_layout.addLayout(output_layout)

        # --- Parameters ---
        params_group = QGroupBox("Parameters")
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)

        # helpers: clickable help link and row builder
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

        # Speedup factor
        self.spin_speedup = NoIMEDoubleSpinBox()
        self.spin_speedup.setRange(0.1, 10.0)
        self.spin_speedup.setSingleStep(0.1)
        self.spin_speedup.setValue(1.0)
        help_speed = "Multiply playback speed. 1.0 = real time; 2.0 = twice as fast. Range: 0.1–10."
        lbl_speed = QLabel("Speedup factor")
        lbl_speed.setToolTip(help_speed)
        self.spin_speedup.setToolTip(help_speed)
        form.addRow(lbl_speed, row_with_help(self.spin_speedup, help_speed))

        # End-of-trial delay
        self.spin_end_delay = NoIMEDoubleSpinBox()
        self.spin_end_delay.setRange(0.0, 20.0)
        self.spin_end_delay.setSingleStep(0.1)
        self.spin_end_delay.setValue(0.5)
        help_end = "Pause on the last frame of each trial before ending the trial."
        lbl_end = QLabel("End-of-trial delay (seconds)")
        lbl_end.setToolTip(help_end)
        self.spin_end_delay.setToolTip(help_end)
        form.addRow(lbl_end, row_with_help(self.spin_end_delay, help_end))

        # Inter-trial delay
        self.spin_inter_delay = NoIMEDoubleSpinBox()
        self.spin_inter_delay.setRange(0.0, 20.0)
        self.spin_inter_delay.setSingleStep(0.1)
        self.spin_inter_delay.setValue(0.2)
        help_inter = "Blank screen between trials."
        lbl_inter = QLabel("Inter-trial delay (seconds)")
        lbl_inter.setToolTip(help_inter)
        self.spin_inter_delay.setToolTip(help_inter)
        form.addRow(lbl_inter, row_with_help(self.spin_inter_delay, help_inter))

        # FPS
        self.spin_fps = NoIMESpinBox()
        self.spin_fps.setRange(1, 30)
        self.spin_fps.setValue(20)
        help_fps = "Video frame rate. Higher = smoother but larger file."
        lbl_fps = QLabel("Frames per second")
        lbl_fps.setToolTip(help_fps)
        self.spin_fps.setToolTip(help_fps)
        form.addRow(lbl_fps, row_with_help(self.spin_fps, help_fps))

        # Dot size
        self.spin_dot_size = NoIMESpinBox()
        self.spin_dot_size.setRange(1, 30)
        self.spin_dot_size.setValue(5)
        help_dot = "Marker size for plotted points (visual ‘ink’ thickness)."
        lbl_dot = QLabel("Dot size")
        lbl_dot.setToolTip(help_dot)
        self.spin_dot_size.setToolTip(help_dot)
        form.addRow(lbl_dot, row_with_help(self.spin_dot_size, help_dot))

        # Pressure threshold
        self.spin_pressure = NoIMESpinBox()
        self.spin_pressure.setRange(1, 100)
        self.spin_pressure.setValue(100)
        help_press = "Highest pressure value (mapped to black color in white background or vice versa). " + \
                     "Higher pressure values are cropped. Lower values are plotted as gray shades. Range: 1–100."
        lbl_press = QLabel("Maximal pressure value")
        lbl_press.setToolTip(help_press)
        self.spin_pressure.setToolTip(help_press)
        form.addRow(lbl_press, row_with_help(self.spin_pressure, help_press))

        # Background color
        self.combo_bg = QComboBox()
        self.combo_bg.addItems(["White", "Black"])
        help_bg = "White = black/gray ink on white; Black = inverted (white/gray ink on black)."
        lbl_bg = QLabel("Background color")
        lbl_bg.setToolTip(help_bg)
        self.combo_bg.setToolTip(help_bg)
        form.addRow(lbl_bg, row_with_help(self.combo_bg, help_bg))

        # Movie maximal size (plot_area_max_size)
        size_row_widget = QWidget()
        size_row = QHBoxLayout(size_row_widget)
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.addWidget(QLabel("width:"))
        self.spin_max_w = NoIMEDoubleSpinBox()
        self.spin_max_w.setRange(0.5, 50.0)
        self.spin_max_w.setSingleStep(0.5)
        self.spin_max_w.setValue(5.0)
        size_row.addWidget(self.spin_max_w)
        size_row.addSpacing(12)
        size_row.addWidget(QLabel("height:"))
        self.spin_max_h = NoIMEDoubleSpinBox()
        self.spin_max_h.setRange(0.5, 50.0)
        self.spin_max_h.setSingleStep(0.5)
        self.spin_max_h.setValue(4.0)
        size_row.addWidget(self.spin_max_h)
        help_size = "Maximal plot area (inches) used for the dots region before margins; controls scale relative to dot size."
        lbl_size = QLabel("Video max. size (inches)")
        lbl_size.setToolTip(help_size)
        form.addRow(lbl_size, row_with_help(size_row_widget, help_size))

        # Title row
        title_row_widget = QWidget()
        title_row = QHBoxLayout(title_row_widget)
        title_row.setContentsMargins(0, 0, 0, 0)
        self.title_lineedit = QLineEdit()
        self.title_lineedit.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.title_lineedit.setPlaceholderText("Enter title or use {keywords}")
        help_trial_title = "Title to show on each trial (empty = no title). To include values from trials.csv, use {column_name}"
        self.title_lineedit.setToolTip(help_trial_title)
        self.title_lineedit.setMinimumWidth(600)
        self.title_lineedit.setText("Trial #{trial_id}")
        self.btn_preview_titles = QPushButton("preview")
        self.btn_preview_titles.setToolTip("Preview what the trial titles are going to look like")
        title_row.addWidget(self.title_lineedit)
        title_row.addWidget(help_link(help_trial_title))
        title_row.addWidget(self.btn_preview_titles)
        form.addRow(QLabel("Trial title"), title_row_widget)

        params_group.setLayout(form)
        main_layout.addWidget(params_group)

        # --- Start button ---
        self.btn_prepare_movie = QPushButton("Prepare movie!")
        self.btn_prepare_movie.setEnabled(False)
        main_layout.addWidget(self.btn_prepare_movie)

        uiu.add_copyright_msg(main_layout)

        self._disable_ime_on_editors()
        self.init_button_operations()
        self.generating = False

    #-----------------------------------------------------------------
    def closeEvent(self, event):
        super().closeEvent(event)
        if not self.generating:
            QApplication.instance().quit()

    #-----------------------------------------------------------------
    def _disable_ime_on_editors(self):
        # Text fields
        self.title_lineedit.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.output_lineedit.setAttribute(Qt.WA_InputMethodEnabled, False)  # readOnly but safe

        # Spin boxes expose an internal QLineEdit
        for sb in (self.spin_speedup, self.spin_end_delay, self.spin_inter_delay, self.spin_fps, self.spin_dot_size, self.spin_pressure,
            self.spin_max_w, self.spin_max_h):
            le = sb.lineEdit()
            if le is not None:
                le.setAttribute(Qt.WA_InputMethodEnabled, False)

    #-----------------------------------------------------------------
    # noinspection PyUnresolvedReferences
    def init_button_operations(self):
        self.btn_add.clicked.connect(self.on_clicked_add_files)
        self.btn_remove.clicked.connect(self.on_clicked_remove_selected)
        self.btn_up.clicked.connect(self.on_clicked_move_up)
        self.btn_down.clicked.connect(self.on_clicked_move_down)
        self.btn_output_file.clicked.connect(self.on_clicked_select_output_file)
        self.list_widget.itemSelectionChanged.connect(self.update_prepare_button)
        self.output_lineedit.textChanged.connect(self.update_prepare_button)
        self.btn_prepare_movie.clicked.connect(self.on_clicked_prepare_movie)
        self.btn_preview_titles.clicked.connect(self.on_clicked_preview_titles)

    #-----------------------------------------------------------------
    def on_clicked_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select CSV files", "", "CSV Files (*.csv)")
        if files:
            items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
            items.extend(files)
            items = list(dict.fromkeys(items))  # remove duplicates, keep order
            self.list_widget.clear()
            self.list_widget.addItems(items)
        self.update_prepare_button()

    #-----------------------------------------------------------------
    def on_clicked_remove_selected(self):
        for item in reversed(self.list_widget.selectedItems()):
            self.list_widget.takeItem(self.list_widget.row(item))
        self.update_prepare_button()

    #-----------------------------------------------------------------
    def on_clicked_move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)

    #-----------------------------------------------------------------
    def on_clicked_move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)

    #-----------------------------------------------------------------
    def on_clicked_select_output_file(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Select output movie file", "", "MP4 Files (*.mp4)")
        if filename:
            if not filename.lower().endswith(".mp4"):
                filename += ".mp4"
            self.output_lineedit.setText(filename)
        self.update_prepare_button()

    #-----------------------------------------------------------------
    def update_prepare_button(self):
        list_not_empty = self.list_widget.count() > 0
        output_not_empty = bool(self.output_lineedit.text().strip())
        self.btn_prepare_movie.setEnabled(list_not_empty and output_not_empty)

    #-----------------------------------------------------------------
    def on_clicked_prepare_movie(self):
        input_files = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        output_file = self.output_lineedit.text().strip()

        config = dict(
            speedup_factor=self.spin_speedup.value(),
            end_of_dataset_delay=self.spin_end_delay.value(),
            inter_dataset_delay=self.spin_inter_delay.value(),
            fps=self.spin_fps.value(),
            point_size=self.spin_dot_size.value(),
            black_pressure=self.spin_pressure.value(),
            invert=(self.combo_bg.currentText() == "Black"),
            plot_area_max_size=(self.spin_max_w.value(), self.spin_max_h.value()),
        )

        title_format = self.title_lineedit.text().strip()

        self.generating = True
        self.close()
        progress_dialog = PrepareMovieProgressDialog(input_files, output_file, config, title_format)
        progress_dialog.start_plotting()
        progress_dialog.exec_()

    #-----------------------------------------------------------------
    def on_clicked_preview_titles(self):
        input_files = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        title_format = self.title_lineedit.text().strip()

        try:
            titles, warnings = generate_titles_for_files(input_files, title_format)

            preview_dialog = QDialog(self)
            preview_dialog.setWindowTitle("Preview Titles")
            preview_dialog.resize(900, 500)
            layout = QVBoxLayout(preview_dialog)

            table = QTableWidget(len(input_files), 2)
            table.setHorizontalHeaderLabels(["Filename", "Resolved Title"])
            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            for i, f in enumerate(input_files):
                table.setItem(i, 0, QTableWidgetItem(os.path.basename(f)))
                table.setItem(i, 1, QTableWidgetItem(titles[i]))
            layout.addWidget(table)

            if warnings:
                for w in warnings:
                    QMessageBox.warning(self, "Warning", w)

            btn_close = QPushButton("Close")
            btn_close.clicked.connect(preview_dialog.close)
            layout.addWidget(btn_close)

            preview_dialog.exec_()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


#---------------------------------------------------------------------------------------------------
class PrepareMovieProgressDialog(QDialog):

    #-----------------------------------------------------------------
    def __init__(self, input_files, output_file, config, title_format):
        super().__init__()
        self.setWindowTitle("Writracker: Movie plotter")
        self.input_files = input_files
        self.output_file = output_file
        self.config = config
        self.title_format = title_format

        self.resize(500, 350)
        layout = QVBoxLayout(self)

        self.top_label = QLabel("Preparing movie…")
        layout.addWidget(self.top_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.message_box = QTextEdit()
        self.message_box.setReadOnly(True)
        self.message_box.setFixedHeight(self.message_box.fontMetrics().lineSpacing() * 12)
        layout.addWidget(self.message_box)

        button_layout = QHBoxLayout()
        self.btn_reveal = QPushButton("preparing…")
        self.btn_reveal.setEnabled(False)
        self.btn_cancel = QPushButton("Cancel")
        button_layout.addWidget(self.btn_reveal)
        button_layout.addWidget(self.btn_cancel)
        layout.addLayout(button_layout)

        self.btn_reveal.clicked.connect(self.reveal_in_finder)
        self.btn_cancel.clicked.connect(self.on_clicked_cancel)

        self.runner = None
        self.canceled = False

    #-----------------------------------------------------------------
    def closeEvent(self, event):
        super().closeEvent(event)
        QApplication.instance().quit()

    #-----------------------------------------------------------------
    def start_plotting(self):
        self.runner = PlotRunner(self.input_files, self.output_file, self.config, self.title_format, self)
        self.runner.progress_signal.connect(self.on_progress)
        self.runner.finished_signal.connect(self.on_finished)
        self.runner.start()

    #-----------------------------------------------------------------
    def on_progress(self, percent, msg=None):
        if percent is not None:
            self.progress_bar.setValue(percent)
        if msg:
            self.message_box.append(msg)

    #-----------------------------------------------------------------
    def on_finished(self, success):
        if self.canceled:
            self.top_label.setText("Cancelled; the file may be incomplete.")
        elif success:
            self.top_label.setText("Finished successfully")
        else:
            self.top_label.setText("Error occurred")

        self.btn_cancel.setEnabled(False)
        self.btn_reveal.setText("reveal in finder")
        self.btn_reveal.setEnabled(True)

    #-----------------------------------------------------------------
    def on_clicked_cancel(self):
        if self.runner and self.runner.isRunning():
            self.canceled = True
            self.runner.requestInterruption()
            self.top_label.setText("Cancelling…")
            self.btn_cancel.setEnabled(False)

    #-----------------------------------------------------------------
    def reveal_in_finder(self):
        if os.path.exists(self.output_file):
            try:
                if sys.platform.startswith('darwin'):
                    subprocess.run(["open", "-R", self.output_file])
                elif os.name == 'nt':
                    subprocess.run(["explorer", "/select,", self.output_file])
                else:
                    subprocess.run(["xdg-open", os.path.dirname(self.output_file)])
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open location: {e}")
        else:
            QMessageBox.warning(self, "File not found", "The output file does not exist.")


#---------------------------------------------------------------------------------------------------
class PlotRunner(QThread):

    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool)

    #-----------------------------------------------------------------
    def __init__(self, input_files, output_file, config, title_format, ui):
        super().__init__()
        self.input_files = input_files
        self.output_file = output_file
        self.config = config
        self.title_format = title_format
        self.ui = ui

    #-----------------------------------------------------------------
    # noinspection PyUnresolvedReferences
    def run(self):
        try:
            titles, warnings = generate_titles_for_files(self.input_files, self.title_format)
            for w in warnings:
                self.progress_signal.emit(None, f"Warning: {w}")

            plotter = UIMoviePlotter(self.input_files, self.output_file, titles=titles, progress_cb=self._on_progress, **self.config)
            plotter.plot()
            self.progress_signal.emit(100, "Movie created: " + os.path.basename(self.output_file))
            self.finished_signal.emit(True)
        except Exception as e:
            traceback.print_exc()
            self.progress_signal.emit(0, f"Error: {e}")
            self.finished_signal.emit(False)

    #-----------------------------------------------------------------
    # This callback is invoked inside the worker thread, but we forward to the main thread via signal
    def _on_progress(self, percent, msg):
        self.progress_signal.emit(percent, msg or "")


#---------------------------------------------------------------------------------------------------
#    Title utilities
#---------------------------------------------------------------------------------------------------
def generate_titles_for_files(input_files, title_format):
    warnings = []
    titles = []
    for f in input_files:
        base = os.path.basename(f)
        title_str = title_format if title_format else os.path.splitext(base)[0]
        if "{" not in title_str:
            titles.append(title_str)
            continue

        trials_csv = os.path.join(os.path.dirname(f), "trials.csv")
        if not os.path.isfile(trials_csv):
            warnings.append(f"No trials.csv found for {base}. Using NA.")
            titles.append(_replace_all_keywords_with_na(title_str))
            continue

        with open(trials_csv, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            if 'traj_file_name' not in reader.fieldnames:
                raise ValueError("trials.csv missing required column 'traj_file_name'")

            row = None
            for r in reader:
                if r['traj_file_name'] == base:
                    row = r
                    break

            if row is None:
                warnings.append(f"No matching row in trials.csv for {base}. Using NA.")
                row = {}

            out_title = title_str
            keywords = re.findall(r'\{(\w+)\}', title_str)
            for kw in keywords:
                if kw not in reader.fieldnames:
                    raise ValueError(f"Keyword '{kw}' not found in trials.csv")
                val = row.get(kw, "NA")
                if val == "NA":
                    rep = "NA"
                else:
                    try:
                        num = float(val)
                        rep = ("%g" % num)
                    except ValueError:
                        rep = val
                out_title = out_title.replace("{" + kw + "}", rep)
            titles.append(out_title)
    return titles, warnings


#---------------------------------------------------------------------------------------------------
def _replace_all_keywords_with_na(title_str):
    return re.sub(r"\{\w+\}", "NA", title_str)


#---------------------------------------------------------------------------------------------------
class NoIMEDoubleSpinBox(QDoubleSpinBox):
    def event(self, e):
        if e.type() in (QEvent.InputMethod, QEvent.InputMethodQuery):
            return True
        return super().event(e)


#---------------------------------------------------------------------------------------------------
class NoIMESpinBox(QSpinBox):
    def event(self, e):
        if e.type() in (QEvent.InputMethod, QEvent.InputMethodQuery):
            return True
        return super().event(e)


#---------------------------------------------------------------------------------------------------
class UIMoviePlotter(MoviePlotter):
    """ UI-aware subclass: emits progress to the dialog """

    def __init__(self, *args, progress_cb=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._progress_cb = progress_cb

    def init_progress_bar(self):
        # override to avoid printing to stdout; initialize UI at 0%
        if self._progress_cb:
            self._progress_cb(0, "Starting…")

    def update_progress_bar(self, progress):
        # called frequently during rendering; pipe to UI
        if self._progress_cb:
            try:
                pc = max(0, min(100, int(round(progress))))
            except Exception:
                pc = 0
            self._progress_cb(pc, None)
