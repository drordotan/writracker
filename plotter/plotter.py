from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import uic
from matplotlib.animation import FFMpegWriter
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import sys
import os

global anim

# Input: Trajectory file path.
def animate_trajectory(traj_file):
    def animation_init(a_line, x):  # only required for blitting to give a clean slate.
        a_line.set_ydata([np.nan] * len(x))
        return a_line,

    def animate(i):
        if i < len(raw_points.x):
            if raw_points.pressure[i] != 0:
                xdata.append(tablet_max_res-raw_points.x[i])  # must mirror X axis
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
    tablet_max_res = 2000
    maxx = raw_points.x.max() + xmargin
    minx = raw_points.x.min() - xmargin
    maxy = raw_points.y.max() + ymargin
    miny = raw_points.y.min() - ymargin
    x = np.arange(0, max(maxx, maxy), 1)
    y = np.arange(0, max(maxx, maxy), 1)
    line, = ax.plot(x, y, 'o', markersize=1)
    ax.set(xlim=(tablet_max_res-maxx, tablet_max_res-minx), ylim=(max(0, miny), maxy))
    xdata, ydata = [], []

    # When using plt.show, 'interval' controls the speed of the animation
    anim = animation.FuncAnimation(fig, animate, init_func=animation_init, interval=10, blit=True)
    plt.show()    # to display "live" the animation
    return anim  # required when calling from inside a function


# # not-working-version for mp4 save
# # f = "animation.mp4"
# # writermp4 = animation.FFMpegWriter(fps=60)
# # ani.save(f, writer=writermp4)
#
# # Bellow: A WORKING version to save GIF. need to edit save_count to have the full animation
# f = "animation.gif"
# # save counts > 1000 caused memory error
# ani = animation.FuncAnimation(fig, animate, init_func=init, blit=True, save_count=1000)
# writergif = animation.PillowWriter(fps=40)  # fps > 60  | fps < 15 caused very very slow output. 30-40 fits.
# ani.save(f, writer=writergif)
# # https://holypython.com/how-to-save-matplotlib-animations-the-ultimate-guide/
#
# # Features to add:
# # 1. marker size control
# # 2. Scatter or continuous line
# # 3. Speed
# # 4. choose file


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('plotter_ui.ui', self)
        self.menu_online_help = self.findChild(QAction, 'actionOnline_help')
        self.btn_play = self.findChild(QPushButton, 'btn_play')
        self.btn_convert_gif = self.findChild(QPushButton, 'btn_convert_gif')
        self.combox_trials = self.findChild(QComboBox, 'combox_trials')
        self.btn_quit = self.findChild(QPushButton, 'btn_quit')
        self.init_ui()
        self.choose_trials_file()
        self.trials_file = None

    def init_ui(self):
        # self.setWindowModality(Qt.ApplicationModal)  # Block main windows until OK is pressed
        self.menu_online_help.triggered.connect(self.f_menu_online_help)
        self.btn_play.clicked.connect(self.f_btn_play)
        self.btn_quit.clicked.connect(self.f_btn_quit)
        # self.show() # # This show is needed only if decided to remove the center from main()

    def f_menu_online_help(self):
        qmbox = QMessageBox()
        qmbox.setWindowTitle("Online help")
        qmbox.setTextFormat(Qt.RichText)
        qmbox.setText("<a href='http://mathinklab.org/writracker-recorder/'>"
                      "Press here to visit WriTracker Recorder website</a>")
        qmbox.exec()

    def f_btn_play(self):
        traj_file = self.combox_trials.currentData()
        # global anim
        anim = animate_trajectory(traj_file+".csv")

    def f_btn_convert_gif(self):
        pass

    def f_btn_quit(self):
        print("ok!")

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
                         " | file name: " + trials_dict[key]['file_name']
            self.combox_trials.addItem(combox_str, userData=traj_directory+os.sep+trials_dict[key]['file_name'])
        return True

    def choose_trials_file(self):
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


def main():
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


if __name__ == '__main__':
    main()


