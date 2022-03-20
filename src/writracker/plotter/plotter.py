from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import uic
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import sys
import os

global anim  # declaring this global is a must due to garbage collection bug in matplotlib animation


# Input: Trajectory file path (to read the raw writing from)
# action: "play" will display the animation immediately. "save" will only convert to gif and save it.
# filename: when choosing action="save", insert file name as well.
def animate_trajectory(traj_file, action="play", filename=""):
    def animation_init():  # only required for blitting to give a clean slate.
        line.set_ydata([np.nan] * len(x))
        return line,

    def animate(i):
        if i < len(raw_points.x):
            if raw_points.pressure[i] != 0:
                xdata.append(raw_points.x[i])
                ydata.append(raw_points.y[i])
                line.set_data(xdata, ydata)
        return line,

    fields = ['x', 'y', 'pressure', 'time']
    try:
        raw_points = pd.read_csv(traj_file, usecols=fields)
    except (IOError, FileNotFoundError):
        QMessageBox().critical(None, "Warning! file access error",
                               "WriTracker couldn't load the trajectory file.", QMessageBox.Ok)
        return False
    fig, ax = plt.subplots()
    xmargin = 100
    ymargin = 100
    maxx = raw_points.x.max() + xmargin
    minx = raw_points.x.min() - xmargin
    maxy = raw_points.y.max() + ymargin
    miny = raw_points.y.min() - ymargin
    x = np.arange(0, max(maxx, maxy), 1)
    y = np.arange(0, max(maxx, maxy), 1)
    line, = ax.plot(x, y, 'o', markersize=1)
    ax.set(xlim=(minx, maxx), ylim=(max(0, miny), maxy))
    xdata, ydata = [], []

    if action == "play":
        # When using plt.show, 'interval' controls the speed of the animation
        anim = animation.FuncAnimation(fig, animate, init_func=animation_init, interval=10, blit=True)
        plt.show()    # to display "live" the animation
        return anim   # required when calling from inside a function
    elif action == "save":
        print("WriTracker Plotter: Saving GIF, please wait")
        f = filename+".gif"
        # save_count > 1000 might cause memory error.
        ani = animation.FuncAnimation(fig, animate, init_func=animation_init, blit=True, save_count=1000)
        writergif = animation.PillowWriter(fps=40)  # fps > 60  | fps < 15 caused very very slow output. 30-40 fits.
        ani.save(f, writer=writergif)

    # -----------------------------------------------------------------------------------------------------------------
    # -----------------------------------------------     GUI setup     -----------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.dirname(__file__) + os.sep + 'plotter_ui.ui', self)
        self.menu_online_help = self.findChild(QAction, 'actionOnline_help')
        self.btn_play = self.findChild(QPushButton, 'btn_play')
        self.btn_convert_gif = self.findChild(QPushButton, 'btn_convert_gif')
        self.combox_trials = self.findChild(QComboBox, 'combox_trials')
        self.btn_quit = self.findChild(QPushButton, 'btn_quit')
        self.trials_file = None
        self.destination_folder = None
        self.choose_trials_file()
        self.init_ui()

    def init_ui(self):
        self.menu_online_help.triggered.connect(self.f_menu_online_help)
        self.btn_play.clicked.connect(self.f_btn_play)
        self.btn_convert_gif.clicked.connect(self.f_btn_convert_gif)
        self.btn_quit.clicked.connect(self.f_btn_quit)
        self.setWindowState(Qt.WindowActive)

    # -----------------------------------------------------------------------------------------------------------------
    # -----------------------------------------------  Button Functions -----------------------------------------------

    def f_menu_online_help(self):
        qmbox = QMessageBox()
        qmbox.setWindowTitle("Online help")
        qmbox.setTextFormat(Qt.RichText)
        qmbox.setText("<a href='http://mathinklab.org/writracker-recorder/'>"
                      "Press here to visit WriTracker Recorder website</a>")
        qmbox.exec()

    def f_btn_play(self):
        traj_file = self.combox_trials.currentData()
        self.btn_play.setEnabled(False)
        anim = animate_trajectory(traj_file+".csv", action="play")
        self.btn_play.setEnabled(True)

    def f_btn_convert_gif(self):
        self.btn_convert_gif.setEnabled(False)
        filename, ok = QInputDialog.getText(self, "Filename", "Enter a name for the GIF file")
        if not ok:
            self.btn_convert_gif.setEnabled(True)
            return False
        if not self.choose_destination_folder():
            self.btn_convert_gif.setEnabled(True)
            return False
        traj_file_path = self.combox_trials.currentData()
        anim_file_path = self.destination_folder+os.sep+filename
        response = QMessageBox.question(self, "Notice", "Conversion is slow and might take up to a minute.\n"
                                        "Please be patient. a message will appear when finished",
                                        QMessageBox.Ok | QMessageBox.Cancel)
        if response == QMessageBox.Ok:
            try:
                anim = animate_trajectory(traj_file_path + ".csv", action="save", filename=anim_file_path)
            except ValueError:
                QMessageBox.about(self, "Error", "Error saving as GIF")
            else:
                QMessageBox.about(self, "Notice", "Finished! your animation is now ready in the trajectory directory")
        self.btn_convert_gif.setEnabled(True)

    def f_btn_quit(self):
        self.close()
    # -----------------------------------------------------------------------------------------------------------------

    # Reads trials.csv file and insert the trials into the combo-box.
    def parse_trials_file(self, trials_file_path):
        file_type = os.path.splitext(trials_file_path)[1]
        traj_directory = os.path.split(trials_file_path)[0]
        if file_type != ".csv":    # read as excel file
            df = pd.read_excel(trials_file_path)
        else:  # read as csv
            df = pd.read_csv(trials_file_path)
        trials_dict = df.set_index('trial_id').T.to_dict()
        for key in trials_dict.keys():
            combox_str = "Trial id: "+ str(key) + "| Target: " + trials_dict[key]['target'] +\
                         " | file name: " + trials_dict[key]['traj_file_name']
            self.combox_trials.addItem(combox_str, userData=traj_directory+os.sep+trials_dict[key]['traj_file_name'])
        return True

    def choose_trials_file(self):
        QMessageBox.about(self, "WriTracker Plotter", "Choose trials.csv file.\n"
                                                      "The file should be in the same directory"
                                                      " as the rest of the trajectory_#.csv files")
        while True:
            trials_file = QFileDialog.getOpenFileName(self, 'Choose Trials file', os.getcwd(),
                                                      "CSV files (*.csv);;XLSX files (*.xlsx);;XLS files (*.xls);;")
            if os.access(trials_file[0], os.W_OK | os.X_OK):
                try:
                    with open(trials_file[0]) as self.trials_file:
                        if not self.parse_trials_file(trials_file[0]):
                            raise IOError  # bad targets file format
                        return True
                except (IOError, FileNotFoundError):
                    pass  # Handle IOError as general error, like closing the file selector.
            msg = QMessageBox()
            answer = msg.question(self, "Error", "Load targets file in order to start the session \n"
                                                 "would you like to try another file?",
                                  msg.Yes | msg.No, msg.Yes)
            if answer == msg.Yes:
                continue
            else:
                return False

    def choose_destination_folder(self):
        while True:
            folder = str(QFileDialog.getExistingDirectory(self, "Select a folder to save the animation"))
            if folder:
                path_ok = os.access(folder, os.W_OK | os.X_OK)
                if path_ok:
                    self.destination_folder = folder
                    return True
            msg = QMessageBox()
            answer = msg.question(self, "Error", "The chosen folder is not valid, or doesn't have write permissions \n"
                                                 "would you like to try another folder?",
                                  msg.Yes | msg.No, msg.Yes)
            if answer == msg.Yes:
                continue
            else:
                return False


def run():
    app = QApplication(sys.argv)
    mainform = MainWindow()
    # Set size and center in the middle of the screen:
    mainform.setGeometry(QRect(400, 400, 400, 400))
    fr_gm = mainform.frameGeometry()
    sc_gm = app.desktop().screenGeometry().center()
    fr_gm.moveCenter(sc_gm)
    mainform.move(fr_gm.topLeft())
    mainform.show()
    sys.exit(app.exec_())
