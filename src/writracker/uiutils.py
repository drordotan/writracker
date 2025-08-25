import sys
import PyQt5.QtWidgets as qw
from PyQt5.QtCore import Qt


#-----------------------------------------------------------------------------------------
def screen_size(only_available_area=True):

    app = qw.QApplication.instance() or qw.QApplication(sys.argv)

    screen = app.primaryScreen()

    if only_available_area:
        available_geom = screen.availableGeometry()
        return available_geom.width(), available_geom.height()
    else:
        size = screen.size()
        return size.width(), size.height()


#-----------------------------------------------------------------------------------------
def add_copyright_msg(layout, year, names):
    row = qw.QHBoxLayout()
    row.setAlignment(Qt.AlignCenter)
    s_names = names if isinstance(names, str) else 'to ' + ', '.join(names)
    row.addWidget(qw.QLabel(f'copyright © {year} {s_names}'))
    mtl_label = qw.QLabel('<a href="http://mathinklab.org/writracker">mathinklab.org</a>')
    mtl_label.setOpenExternalLinks(True)
    mtl_label.setTextFormat(Qt.RichText)
    mtl_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
    row.addWidget(mtl_label)
    layout.addLayout(row)
