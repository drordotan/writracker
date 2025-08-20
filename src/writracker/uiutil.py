import sys
import PyQt5.QtWidgets as qw


def screen_size(only_available_area=True):

    app = qw.QApplication.instance() or qw.QApplication(sys.argv)

    screen = app.primaryScreen()

    if only_available_area:
        available_geom = screen.availableGeometry()
        return available_geom.width(), available_geom.height()
    else:
        size = screen.size()
        return size.width(), size.height()
