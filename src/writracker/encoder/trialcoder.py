"""
coding strokes & characters in one trial - PyQt5 version (full file)
Contains full key handling parity with the original PySimpleGUI version:
- Letter shortcuts (English + Hebrew)
- ENTER confirms / ESC cancels when a selection command is active.
"""
import traceback
import sys
import numpy as np
import re
import enum
import PyQt5.QtWidgets as qw
from PyQt5.QtCore import Qt, QPointF, pyqtSignal
from PyQt5.QtGui import QPen, QBrush, QColor

from writracker.encoder import dataio, manip
import writracker.uiutils as uiu


#======================================================================================================
# Config & constants
#======================================================================================================

class ResponseMandatory(enum.Enum):
    Optional = 0
    Mandatory = 1
    MandatoryForAll = 2


_response_mandatory_options = 'Optional', 'Mandatory only for correct trials', 'Mandatory for correct and error trials'

app_config = dict(
    max_within_char_overlap=0.33,
    error_codes=('WrongNumber', 'NoResponse', 'BadHandwriting', 'TooConnected'),
    response_mandatory=ResponseMandatory.Mandatory,
    show_extending=True,
    dot_radius=3
)

CYANS = ["#00FFFF", "#A0FFFF", "#C0FFFF"]
PURPLES = ["#BF0FF8", "#CE54F5", "#E191FA"]

ORANGES = ["#FF8B00", "#FF7F00", "#FF6600"]
REDS = ["#FF0000", "#FF8080", "#FFA0A0"]

RED = "#FF0000"
GREEN = "#00FF00"
YELLOW = "#FFFF00"


#======================================================================================================
# noinspection PyUnresolvedReferences
class SettingsDialog(qw.QDialog):

    #---------------------------------------------------------------------------------------
    def __init__(self, parent=None, show_cancel_button=True):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setModal(True)
        self.show_cancel_button = show_cancel_button
        self.setup_ui()

    #---------------------------------------------------------------------------------------
    # noinspection PyAttributeOutsideInit
    def setup_ui(self):
        layout = qw.QVBoxLayout()

        # Warning label
        self.warning_label = qw.QLabel()
        self.warning_label.setStyleSheet("color: red;")
        layout.addWidget(self.warning_label)

        # Response mandatory
        row = qw.QHBoxLayout()
        row.addWidget(qw.QLabel("Typing in the participants' response is "))
        self.response_mandatory_combo = qw.QComboBox()
        self.response_mandatory_combo.addItems(_response_mandatory_options)
        self.response_mandatory_combo.setCurrentIndex(app_config['response_mandatory'].value)
        row.addWidget(self.response_mandatory_combo)
        layout.addLayout(row)

        # Max within char overlap
        row = qw.QHBoxLayout()
        row.addWidget(qw.QLabel('Merge 2 strokes into one character if their horizontal overlap exceeds'))
        self.overlap_input = qw.QLineEdit('{:.1f}'.format(100 * app_config['max_within_char_overlap']))
        row.addWidget(self.overlap_input)
        row.addWidget(qw.QLabel('percent'))
        layout.addLayout(row)

        # Error codes
        row = qw.QHBoxLayout()
        row.addWidget(qw.QLabel('Error codes (comma-separated list): '))
        self.error_codes_input = qw.QLineEdit(','.join(app_config['error_codes']))
        row.addWidget(self.error_codes_input)
        layout.addLayout(row)

        # Dot radius
        row = qw.QHBoxLayout()
        row.addWidget(qw.QLabel('The size of dots for plotting the trajectories: '))
        self.dot_radius_combo = qw.QComboBox()
        self.dot_radius_combo.addItems(['1', '2', '3', '4', '5'])
        self.dot_radius_combo.setCurrentText(str(app_config['dot_radius']))
        row.addWidget(self.dot_radius_combo)
        layout.addLayout(row)

        # Buttons
        row = qw.QHBoxLayout()
        ok_btn = qw.QPushButton('OK')
        ok_btn.clicked.connect(self.accept)
        row.addWidget(ok_btn)

        if self.show_cancel_button:
            cancel_btn = qw.QPushButton('Cancel')
            cancel_btn.clicked.connect(self.reject)
            row.addWidget(cancel_btn)

        layout.addLayout(row)

        add_copyright(layout)

        self.setLayout(layout)

    #---------------------------------------------------------------------------------------
    def get_values(self):
        return {
            'response_mandatory': self.response_mandatory_combo.currentText(),
            'max_within_char_overlap': self.overlap_input.text(),
            'error_codes': self.error_codes_input.text(),
            'dot_radius': self.dot_radius_combo.currentText()
        }

    #---------------------------------------------------------------------------------------
    def set_warning(self, text):
        self.warning_label.setText(text)


#---------------------------------------------------------------------------------------
def show_settings_screen(show_cancel_button=True):

    # qw.QApplication.instance() or qw.QApplication(sys.argv)

    warning = ''

    while True:
        dialog = SettingsDialog(show_cancel_button=show_cancel_button)
        dialog.set_warning(warning)

        if dialog.exec_() != qw.QDialog.Accepted:
            break

        values = dialog.get_values()
        try:
            max_within_char_overlap = float(values['max_within_char_overlap'])
        except ValueError:
            warning = 'Invalid "Maximal overlap" value'
            continue

        if not (0 < max_within_char_overlap < 100):
            warning = 'Invalid "Maximal overlap" value (expecting a value between 0 and 100)'
            continue

        error_codes = values['error_codes']
        if not re.match(r'([a-zA-Z_]+)(,[a-zA-Z_]+)*', error_codes):
            warning = 'Error codes must be a comma-separated list of letter codes, without spaces'
            continue

        app_config['response_mandatory'] = ResponseMandatory(_response_mandatory_options.index(values['response_mandatory']))
        app_config['max_within_char_overlap'] = max_within_char_overlap / 100
        app_config['error_codes'] = error_codes.split(',')  # type: ignore
        app_config['dot_radius'] = int(values['dot_radius'])

        break


#======================================================================================================
# noinspection PyUnresolvedReferences
class GraphicsView(qw.QGraphicsView):

    clicked = pyqtSignal(QPointF)

    #---------------------------------------------------------------------------------------
    def __init__(self):
        super().__init__()
        self.scene = qw.QGraphicsScene()
        self.setScene(self.scene)
        self.setBackgroundBrush(QBrush(QColor('black')))

    #---------------------------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self.clicked.emit(scene_pos)
        super().mousePressEvent(event)


#======================================================================================================
# noinspection PyUnresolvedReferences,PyAttributeOutsideInit
class TrialEncodingWindow(qw.QMainWindow):
    
    #---------------------------------------------------------------------------------------
    def __init__(self, trial, characters, sub_trial_num, screen_size, user_response=''):
        super().__init__()
        self.trial = trial
        self.characters = characters
        self.sub_trial_num = sub_trial_num
        self.screen_size = screen_size
        self.user_response = user_response
        self.selection_handler = None
        self.current_command = None
        self.result = 'continue'
        self.extra_info = None

        self.setup_ui()
        self.setup_connections()
        self.setup_keyboard_shortcuts()

    #---------------------------------------------------------------------------------------
    def setup_ui(self):

        title = 'Trial #{}, target={} ({} characters, {} strokes)'.format(
            self.trial.trial_id, self.trial.stimulus,
            len([c for c in self.characters if len(c.trajectory) > 0]),
            len([s for c in self.characters for s in c.on_paper_strokes if len(s.trajectory) > 0])
        )
        self.setWindowTitle(title)

        central = qw.QWidget()
        self.setCentralWidget(central)
        layout = qw.QVBoxLayout(central)

        self.instructions_label = qw.QLabel(' ' * 200)
        self.instructions_label.setStyleSheet("color: white; font-size: 16px;")
        layout.addWidget(self.instructions_label)

        self.graphics_view = GraphicsView()
        self.graphics_view.setFixedSize(self.screen_size[0], self.screen_size[1])
        layout.addWidget(self.graphics_view)

        # Trial-level
        row = qw.QHBoxLayout()
        row.addWidget(qw.QLabel('Trial-level: '))
        self.reset_button = qw.QPushButton('(R)eset current trial')
        self.split_trial_button = qw.QPushButton('Split (T)rial')
        self.split_stroke_button = qw.QPushButton('Split (S)troke')
        self.delete_stroke_button = qw.QPushButton('(D)elete stroke')
        self.rotate_hor_button = qw.QPushButton('(H)orizontally')
        self.rotate_ver_button = qw.QPushButton('(V)ertically')
        row.addWidget(self.reset_button)
        row.addWidget(self.split_trial_button)
        row.addWidget(qw.QLabel('Stroke-level: '))
        row.addWidget(self.split_stroke_button)
        row.addWidget(self.delete_stroke_button)
        row.addWidget(qw.QLabel('Rotate trial: '))
        row.addWidget(self.rotate_hor_button)
        row.addWidget(self.rotate_ver_button)
        layout.addLayout(row)

        # Character-level
        row = qw.QHBoxLayout()
        row.addWidget(qw.QLabel('Character-level: '))
        self.split_char_button = qw.QPushButton('Split (C)har')
        self.merge_chars_button = qw.QPushButton('(M)erge chars')
        self.extend_char_button = qw.QPushButton('E(x)tend char')
        self.show_extending_checkbox = qw.QCheckBox('Show extending chars')
        self.show_extending_checkbox.setChecked(app_config['show_extending'])
        row.addWidget(self.split_char_button)
        row.addWidget(self.merge_chars_button)
        row.addWidget(self.extend_char_button)
        row.addWidget(self.show_extending_checkbox)
        layout.addLayout(row)

        # Navigation / decision
        row = qw.QHBoxLayout()
        row.addWidget(qw.QLabel('Navigation / decision: '))
        self.accept_button = qw.QPushButton('(A)ccept as OK')
        self.accept_error_button = qw.QPushButton('Err(o)r:')
        self.accept_error_button.setEnabled(False)
        self.error_combo = qw.QComboBox()
        self.error_combo.addItems(['Choose one...'] + app_config['error_codes'])  # type: ignore
        self.skip_button = qw.QPushButton('s(K)ip current trial')
        self.prev_button = qw.QPushButton('(P)revious trial')
        self.goto_button = qw.QPushButton('(G)o to specific trial')
        row.addWidget(self.accept_button)
        row.addWidget(self.accept_error_button)
        row.addWidget(self.error_combo)
        row.addWidget(self.skip_button)
        row.addWidget(self.prev_button)
        row.addWidget(self.goto_button)
        layout.addLayout(row)

        # Response
        row = qw.QHBoxLayout()
        row.addWidget(qw.QLabel('User response:'))
        self.response_input = qw.QLineEdit(self.user_response)
        self.response_input.setReadOnly(True)
        self.response_input.setStyleSheet("background-color: #CFCFCF;")
        self.update_response_button = qw.QPushButton('Update...')
        self.confirm_button = qw.QPushButton('Confirm')
        self.cancel_button = qw.QPushButton('Cancel')
        row.addWidget(self.response_input)
        row.addWidget(self.update_response_button)
        row.addWidget(qw.QLabel('Confirm split/merge:'))
        row.addWidget(self.confirm_button)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

        # General
        row = qw.QHBoxLayout()
        self.settings_button = qw.QPushButton('S(E)ttings')
        self.quit_button = qw.QPushButton('(Q)uit WEncoder')
        row.addWidget(self.settings_button)
        row.addWidget(self.quit_button)
        layout.addLayout(row)

        add_copyright(layout)

        on_paper_chars = [c for c in self.characters if len(c.trajectory) > 0]
        if len(on_paper_chars) < 2:
            self.merge_chars_button.setEnabled(False)
            self.split_trial_button.setEnabled(False)

        # Make sure main window receives keyboard focus
        self.setFocusPolicy(Qt.StrongFocus)
        self.graphics_view.setFocusPolicy(Qt.NoFocus)
        self.response_input.setFocusPolicy(Qt.ClickFocus)

        self.resize(self.screen_size[0] + 50, self.screen_size[1] + 300)

    #---------------------------------------------------------------------------------------
    def setup_connections(self):
        self.graphics_view.clicked.connect(self.on_graph_clicked)

        # Buttons → commands
        self.reset_button.clicked.connect(lambda: self.handle_command('reset_trial'))
        self.split_trial_button.clicked.connect(lambda: self.handle_command('split_trial'))
        self.split_stroke_button.clicked.connect(lambda: self.handle_command('split_stroke'))
        self.delete_stroke_button.clicked.connect(lambda: self.handle_command('delete_stroke'))
        self.rotate_hor_button.clicked.connect(lambda: self.handle_command('rotate_hor'))
        self.rotate_ver_button.clicked.connect(lambda: self.handle_command('rotate_ver'))

        self.split_char_button.clicked.connect(lambda: self.handle_command('split_char'))
        self.merge_chars_button.clicked.connect(lambda: self.handle_command('merge_chars'))
        self.extend_char_button.clicked.connect(lambda: self.handle_command('set_extending_chars'))
        self.show_extending_checkbox.toggled.connect(self.on_show_extending_changed)

        self.accept_button.clicked.connect(lambda: self.handle_command('accept'))
        self.accept_error_button.clicked.connect(lambda: self.handle_command('accept_error'))
        self.error_combo.currentTextChanged.connect(self.on_error_code_changed)
        self.skip_button.clicked.connect(lambda: self.handle_command('skip_trial'))
        self.prev_button.clicked.connect(lambda: self.handle_command('prev_trial'))
        self.goto_button.clicked.connect(lambda: self.handle_command('choose_trial'))

        self.update_response_button.clicked.connect(lambda: self.handle_command('enter_response'))
        self.confirm_button.clicked.connect(lambda: self.handle_command('confirm'))
        self.cancel_button.clicked.connect(lambda: self.handle_command('cancel'))

        self.settings_button.clicked.connect(lambda: self.handle_command('settings'))
        self.quit_button.clicked.connect(lambda: self.handle_command('quit'))

    #---------------------------------------------------------------------------------------
    def setup_keyboard_shortcuts(self):
        # Map letters (English + Hebrew) to commands
        self._keymap_text = {
            # Trial-level / nav
            'r': 'reset_trial',   'ר': 'reset_trial',
            'g': 'choose_trial',  'ע': 'choose_trial',
            'e': 'settings',      'ק': 'settings',
            'q': 'quit',
            # Decisions
            'a': 'accept',        'ש': 'accept',
            'o': 'accept_error',  'ם': 'accept_error',
            'k': 'skip_trial',    'ל': 'skip_trial',
            'p': 'prev_trial',    'פ': 'prev_trial',
            # Edit operations
            'm': 'merge_chars',   'צ': 'merge_chars',
            's': 'split_stroke',  'ד': 'split_stroke',
            'c': 'split_char',    'ב': 'split_char',
            't': 'split_trial',   'א': 'split_trial',
            'x': 'set_extending_chars', 'ס': 'set_extending_chars',
            'h': 'rotate_hor',    'י': 'rotate_hor',
            'v': 'rotate_ver',    'ה': 'rotate_ver',
            'd': 'delete_stroke', 'ג': 'delete_stroke',
        }

    #---------------------------------------------------------------------------------------
    # --- keyboard handling ---
    def keyPressEvent(self, event):
        key = event.key()
        text = event.text()

        # If a selection command is active: ENTER confirms, ESC cancels
        if self.current_command is not None:
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.handle_command('confirm')
                event.accept()
                return
            if key == Qt.Key_Escape:
                self.handle_command('cancel')
                event.accept()
                return

        # Handle ENTER/ESC even without active command (safe no-op)
        if key in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        if key == Qt.Key_Escape:
            event.accept()
            return

        # Letter keys (normalize to lower case)
        if text:
            cmd = self._keymap_text.get(text.lower())
            if cmd:
                self.handle_command(cmd)
                event.accept()
                return

        super().keyPressEvent(event)

    # --- mouse click on graphics view ---
    def on_graph_clicked(self, pos):
        if self.selection_handler is not None:
            self.selection_handler.clicked({'graph': (pos.x(), pos.y())})

    def on_show_extending_changed(self, checked):
        app_config['show_extending'] = checked
        self.result = 'rerun'
        self.close()

    def on_error_code_changed(self, text):
        self.accept_error_button.setEnabled(text in app_config["error_codes"])

    # --- command dispatcher ---
    def handle_command(self, command):
        if command == 'reset_trial':
            ans = qw.QMessageBox.question(self, 'Reset trial', 'Are you sure you want to reset the current trial?',
                                          qw.QMessageBox.Yes | qw.QMessageBox.No)
            if ans == qw.QMessageBox.Yes:
                self.result = 'reset_trial'
                self.close()

        elif command == 'quit':
            if qw.QMessageBox.question(self, 'Quit', 'Are you sure you want to quit WEncoder?',
                                    qw.QMessageBox.Yes | qw.QMessageBox.No) == qw.QMessageBox.Yes:
                self.result = 'quit'
                self.close()

        elif command == 'choose_trial':
            self.result = 'choose_trial'
            self.close()

        elif command == 'settings':
            self.result = 'settings'
            self.close()

        elif command == 'accept':
            on_paper_chars = [c for c in self.characters if len(c.trajectory) > 0]
            resp_optional = app_config['response_mandatory'] == ResponseMandatory.Optional
            if not resp_optional:
                response = self.get_valid_user_response(self.user_response, on_paper_chars,
                                                        self.trial.stim_chars, get_if_already_exists=False)
            else:
                response = self.user_response
            if resp_optional or (response is not None and response != ''):
                self.result = 'next_trial'
                self.user_response = response
                self.close()

        elif command == 'accept_error':
            on_paper_chars = [c for c in self.characters if len(c.trajectory) > 0]
            resp_optional = app_config['response_mandatory'] != ResponseMandatory.MandatoryForAll
            if not resp_optional:
                response = self.get_valid_user_response(self.user_response, on_paper_chars,
                                                        self.trial.stim_chars, get_if_already_exists=False)
            else:
                response = self.user_response
            if resp_optional or response is not None:
                self.result = 'next_trial'
                self.user_response = response
                self.extra_info = self.error_combo.currentText()
                self.close()

        elif command == 'skip_trial':
            self.result = 'skip_trial'
            self.close()

        elif command == 'prev_trial':
            self.result = 'prev_trial'
            self.close()

        elif command in ['merge_chars', 'split_stroke', 'split_char', 'split_trial',
                         'set_extending_chars', 'delete_stroke']:
            if self.current_command is None:
                self.start_selection_command(command)

        elif command in ['rotate_hor', 'rotate_ver']:
            if self.current_command is None:
                if command == 'rotate_hor':
                    manip.rotate_horizontally(self.characters)
                else:
                    manip.rotate_vertically(self.characters)
                self.result = 'replace_trial'
                self.extra_info = [self.characters]
                self.close()

        elif command == 'enter_response':
            on_paper_chars = [c for c in self.characters if len(c.trajectory) > 0]
            response = self.get_valid_user_response(self.user_response, on_paper_chars,
                                                    self.trial.stim_chars, get_if_already_exists=True)
            if response is not None:
                self.result = 'rerun'
                self.extra_info = response
                self.close()

        elif command == 'confirm':
            if self.current_command is not None:
                self.handle_confirm()

        elif command == 'cancel':
            if self.current_command is not None:
                self.handle_cancel()

    def start_selection_command(self, command):
        self.current_command = command
        strokes = [s for c in self.characters for s in c.on_paper_strokes]

        if command == 'merge_chars' and len(self.characters) > 1:
            self.instructions_label.setText('Select the characters to merge. ENTER=confirm, ESC=abort')
            self.selection_handler = _CharsSelectorConsecutivePair(self.graphics_view, self.characters)

        elif command == 'split_stroke':
            self.instructions_label.setText('Select a stroke to split. ENTER=confirm, ESC=abort')
            self.selection_handler = _SingleStrokeSelector(self.graphics_view, strokes)

        elif command == 'split_char':
            self.instructions_label.setText('Select a character to split to 2 different characters. ENTER=confirm, ESC=abort')
            self.selection_handler = _MultiStrokeSelector(self.graphics_view, self.characters, 'before')

        elif command == 'split_trial':
            self.instructions_label.setText('Select the last character of trial#1. ENTER=confirm, ESC=abort')
            self.selection_handler = _CharSeriesSelector(self.graphics_view, self.characters)

        elif command == 'set_extending_chars':
            self.instructions_label.setText('Select 2 characters to connect as extending, or 1 char to un-extend. ENTER=confirm, ESC=abort')
            self.selection_handler = _CharSelectorAnyPair(self.graphics_view, self.characters)

        elif command == 'delete_stroke':
            self.instructions_label.setText('Select a stroke to delete. ENTER=confirm, ESC=abort')
            self.selection_handler = _SingleStrokeSelector(self.graphics_view, strokes)

    def handle_confirm(self):
        if self.current_command == 'split_char':
            self.characters = manip.split_character(self.characters,
                                                    self.selection_handler.selected_char,
                                                    self.selection_handler.selected_stroke)
            self.result = 'continue'
            self.close()

        elif self.current_command == 'merge_chars':
            self.characters = manip.merge_characters(self.characters, self.selection_handler.selected)
            self.result = 'continue'
            self.close()

        elif self.current_command == 'split_stroke':
            if self.selection_handler.selected is None:
                self.result = 'continue'
                self.close()
                return
            self.result = 'split_stroke'
            self.extra_info = self.selection_handler.selected
            self.close()

        elif self.current_command == 'split_trial':
            if self.selection_handler.selected is None:
                self.result = 'continue'
                self.close()
                return
            chars1, chars2 = manip.split_into_2_trials(self.characters, self.selection_handler.selected)
            self.result = 'replace_trial'
            self.extra_info = (chars1, chars2)
            self.close()

        elif self.current_command == 'set_extending_chars':
            if len(getattr(self.selection_handler, 'selected_chars', [])) == 0:
                self.result = 'continue'
                self.close()
                return
            _set_extending_characters(self.characters, self.selection_handler)
            self.result = 'rerun'
            self.close()

        elif self.current_command == 'delete_stroke':
            try:
                self.characters, err_msg = manip.delete_stroke(self.characters, self.selection_handler)
                if err_msg is not None:
                    qw.QMessageBox.critical(self, 'Invalid deletion attempt', err_msg)
                self.result = 'rerun'
                self.close()
            except Exception as e:
                traceback.print_exception(e)
                qw.QMessageBox.critical(self, 'Error in WEncoder', f'Error when trying to delete a character: {e}')
                self.result = 'rerun'
                self.close()

    def handle_cancel(self):
        self.instructions_label.setText('')
        self.current_command = None
        if self.selection_handler is not None:
            self.selection_handler.cleanup()
            self.selection_handler = None

    # --- response helper ---
    def get_valid_user_response(self, response, on_paper_chars, target=None, get_if_already_exists=True):
        n_chars = len([c for c in on_paper_chars if c.extends is None])

        orig_response = response
        if response is None:
            response = ''

        default_resp = ''
        if response == '' and target is not None and len(target) == n_chars:
            default_resp = target

        force_get = get_if_already_exists
        while force_get or not self.response_ok(response, n_chars):
            text, ok = qw.QInputDialog.getText(self, 'Enter response',
                                               f'Please enter a response with exactly {n_chars} characters.',
                                               text=default_resp)
            if not ok:
                return orig_response
            elif text == '':
                return ''
            response = text
            force_get = False

        return response

    def response_ok(self, response, n_chars):
        if response is None or response == '':
            return app_config['response_mandatory'] == ResponseMandatory.Optional
        else:
            return len(response) == n_chars


#============================================================================================================================
class CodeSingleTrial(object):
    """
    Handle the flow of encoding a single trial
    """

    #---------------------------------------------------------------------------------------
    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.inner_margin = 25  # The margin required between the most extreme dots and the edges of their plot area (in pixels)
        self.outer_margin = 25  # The margin required between the edges of the plot area and screen edges (in pixels)

    #---------------------------------------------------------------------------------------
    def encode(self, trial):
        """
        Fully encode one trial. If the trial is split in two: encode both halves.
        Return what to do next: quit, next, prev, or choose_trial
        """

        trial_queue = _init_trial_queue(trial)
        sub_trial_num = 1
        user_response_as_text = None

        while len(trial_queue) > 0:
            characters = trial_queue.pop(0)

            rc = 'continue'
            while rc == 'continue':
                rc, characters, extra_info = self._try_encode_trial(trial, characters, sub_trial_num, user_response_as_text)

            user_response_as_text = None

            #-- Variable 'rc' determines what the next action should be

            #-- Quit program
            if rc == 'quit':
                return 'quit'

            #-- Open settings screen
            elif rc == 'settings':
                show_settings_screen()
                trial_queue = _init_trial_queue(trial)
                sub_trial_num = 1

            #-- Open the 'choose trial' popup - this happens outside this function
            elif rc == 'choose_trial':
                return 'choose_trial'

            #-- Reset the currrent trial to its original state
            elif rc == 'reset_trial':
                trial_queue = _init_trial_queue(trial)
                sub_trial_num = 1
                dataio.delete_trial(self.out_dir, trial.trial_id)
                trial.processed = False

            #-- Replace the current trial with a new one
            elif rc == 'replace_trial':
                # noinspection PyUnboundLocalVariable
                for char_list in extra_info[::-1]:
                    trial_queue.insert(0, char_list)

            #-- Continue to the next trial
            elif rc in ('next_trial', 'skip_trial'):
                sub_trial_num += 1

            #-- Return to the previous trial
            elif rc == 'prev_trial':
                return 'prev'

            #-- Open a popup to split a particular stroke into 2 strokes
            elif rc == 'split_stroke':
                stroke = extra_info
                dot = SplitStrokeDialog.run(stroke, self.inner_margin, self.outer_margin)
                if dot is not None:
                    characters = manip.split_stroke(characters, stroke, dot)
                trial_queue.insert(0, characters)

            #-- Just rerun the current trial
            elif rc == 'rerun':
                trial_queue.insert(0, characters)
                user_response_as_text = extra_info

            else:
                raise Exception(f'Bug: unknown rc ({rc})')

        return 'next'

    #---------------------------------------------------------------------------------------
    def _try_encode_trial(self, trial, characters, sub_trial_num, response):

        app = qw.QApplication.instance() or qw.QApplication(sys.argv)

        strokes = [s for c in characters for s in c.on_paper_strokes]
        all_markup_dots = [dot for c in characters for dot in c.on_paper_dots]

        if len(strokes) == 0:
            dataio.save_trial(trial, '', 'empty', characters, sub_trial_num, self.out_dir)
            trial.processed = True
            return 'next_trial', None, None

        on_paper_chars = [c for c in characters if len(c.trajectory) > 0]
        on_paper_strokes = [s for s in strokes if len(s.trajectory) > 0]  # noqa: F841 (kept for parity)

        screen_size = uiu.screen_size()
        expand_ratio, offset, screen_size = _get_expand_ratio(all_markup_dots, screen_size, self.inner_margin, self.outer_margin)

        window = TrialEncodingWindow(trial, characters, sub_trial_num, screen_size, response or '')
        _plot_dots_for_markup(characters, window.graphics_view, screen_size, expand_ratio, offset, self.inner_margin)

        window.show()
        app.exec_()

        # Save if accepted
        if window.result == 'next_trial':
            # Determine if OK or Error by presence of extra_info (error code)
            if window.extra_info in (None, '',):
                if sub_trial_num == 1:
                    dataio.delete_trial(self.out_dir, trial.trial_id)
                dataio.save_trial(trial, window.user_response, "OK", window.characters, sub_trial_num, self.out_dir)
                trial.processed = True
            else:
                if sub_trial_num == 1:
                    dataio.delete_trial(self.out_dir, trial.trial_id)
                dataio.save_trial(trial, window.user_response, window.extra_info, window.characters, sub_trial_num, self.out_dir)
                trial.processed = True

        return window.result, window.characters, window.extra_info


#---------------------------------------------------------------------------------------
def _init_trial_queue(trial):
    return [manip.create_default_characters(trial.traj_points, app_config['max_within_char_overlap'])]


#======================================================================================================
# noinspection PyUnresolvedReferences,PyAttributeOutsideInit
class SplitStrokeDialog(qw.QDialog):

    #---------------------------------------------------------------------------------------
    @staticmethod
    def run(stroke, inner_margin, outer_margin, dot_radius=6):
        screen_size = uiu.screen_size()
        expand_ratio, offset, screen_size = _get_expand_ratio(stroke, screen_size, inner_margin, outer_margin)
        window = SplitStrokeDialog(stroke, screen_size, expand_ratio, offset, inner_margin, dot_radius)
        if window.exec_() == qw.QDialog.Accepted:
            return window.selected_dot.dot if window.selected_dot is not None else None

        return None

    #---------------------------------------------------------------------------------------
    def __init__(self, stroke, screen_size, expand_ratio, offset, margin, dot_radius=6):
        super().__init__()
        self.stroke = stroke
        self.expand_ratio = expand_ratio
        self.offset = offset
        self.margin = margin
        self.dot_radius = dot_radius
        self.selected_dot = None
        self.dots = []

        self.setWindowTitle('Split a stroke into two strokes')
        self.setModal(True)
        self.setup_ui(screen_size)
        self.plot_dots()

    #---------------------------------------------------------------------------------------
    def setup_ui(self, screen_size):
        layout = qw.QVBoxLayout()
        instructions = qw.QLabel('Choose a dot on which the stroke will be split. ENTER=confirm, ESC=abort')
        instructions.setStyleSheet("color: red;")
        layout.addWidget(instructions)

        self.graphics_view = GraphicsView()
        self.graphics_view.setFixedSize(screen_size[0], screen_size[1])
        self.graphics_view.clicked.connect(self.on_graph_clicked)
        layout.addWidget(self.graphics_view)

        row = qw.QHBoxLayout()
        self.confirm_button = qw.QPushButton('Confirm')
        self.cancel_button = qw.QPushButton('Cancel')
        self.confirm_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        row.addWidget(self.confirm_button)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

        self.setLayout(layout)

    #---------------------------------------------------------------------------------------
    def plot_dots(self):
        self.dots = _plot_dots_for_split(self.stroke.trajectory, self.graphics_view,
                                         (self.graphics_view.width(), self.graphics_view.height()),
                                         self.expand_ratio, self.offset, self.margin, self.dot_radius)

    #---------------------------------------------------------------------------------------
    def on_graph_clicked(self, pos):
        click_coord = (pos.x(), pos.y())
        clicked_dot = _find_dot_closest_to(self.dots, click_coord)
        # reset
        for dot in self.dots:
            if hasattr(dot, 'graphics_item'):
                dot.graphics_item.setBrush(QBrush(QColor(dot.color)))
        # highlight up to clicked
        for dot in self.dots:
            if dot.t <= clicked_dot.t and hasattr(dot, 'graphics_item'):
                dot.graphics_item.setBrush(QBrush(QColor('#00FF00')))
        self.selected_dot = clicked_dot

    #---------------------------------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


#======================================================================================================
# Plotting helpers
#======================================================================================================

#---------------------------------------------------------------------------------------
def _plot_dots_for_markup(characters, graphics_view, screen_size, expand_ratio, offset, margin):

    dot_radius = app_config['dot_radius']
    scene = graphics_view.scene
    scene.clear()

    char_index = 0
    for char in characters:
        char_index += 1
        strokes = char.on_paper_strokes

        if char.extends is None:
            color = ORANGES if char.char_num % 2 == 1 else CYANS
        elif not app_config['show_extending']:
            continue
        else:
            color = REDS if char.char_num % 2 == 1 else PURPLES

        last_x, last_y = 0, 0
        for i in range(len(strokes)):
            stroke = strokes[i]
            stroke.color = color[i] if i < len(color) else color[-1]

            for dot in stroke.trajectory:
                x = (dot.x - offset[0]) * expand_ratio + margin
                y = (dot.y - offset[1]) * expand_ratio + margin
                dot.screen_x = x
                dot.screen_y = y

                ellipse = qw.QGraphicsEllipseItem(x - dot_radius, y - dot_radius, dot_radius * 2, dot_radius * 2)
                ellipse.setBrush(QBrush(QColor(stroke.color)))
                ellipse.setPen(QPen(QColor(stroke.color)))
                scene.addItem(ellipse)
                dot.ui = ellipse
                last_x, last_y = x, y

            stroke_name = "{}.{}".format(char_index, i + 1)
            if char.extends is not None:
                stroke_name += "(E{})".format(char.extends)
            label = qw.QGraphicsTextItem(stroke_name)
            label.setDefaultTextColor(QColor('yellow'))
            label.setPos(last_x + 2, last_y + 2)
            scene.addItem(label)


#---------------------------------------------------------------------------------------
def _plot_dots_for_split(dot_list, graphics_view, screen_size, expand_ratio, offset, margin, dot_radius=6, n_colors=10):

    scene = graphics_view.scene
    scene.clear()

    darkest_color = 100
    color_range = 255 - darkest_color

    dots = np.array(dot_list)
    ui_dots = []

    z = np.array([dot.z for dot in dots])
    z = np.round(z / max(z) * n_colors)

    for z_level in range(n_colors + 1):
        curr = dots[z == z_level]
        if len(curr) == 0:
            continue

        color = round(darkest_color + color_range * (z_level / n_colors))
        color_hex = "#" + ("%02x" % color) * 3

        for dot in curr:
            uidot = UiTrajPointForSplit(dot, color_hex)
            x = (dot.x - offset[0]) * expand_ratio + margin
            y = (dot.y - offset[1]) * expand_ratio + margin
            uidot.screen_x = x
            uidot.screen_y = y

            ellipse = qw.QGraphicsEllipseItem(x - dot_radius, y - dot_radius, dot_radius * 2, dot_radius * 2)
            ellipse.setBrush(QBrush(QColor(color_hex)))
            ellipse.setPen(QPen(QColor(color_hex)))
            scene.addItem(ellipse)
            uidot.graphics_item = ellipse
            ui_dots.append(uidot)

    return ui_dots


#---------------------------------------------------------------------------------------
class UiTrajPointForSplit(object):
    """ A single trajectory point in the split-stroke dialog """

    def __init__(self, dot, color):
        self.dot = dot
        self.color = color
        self.graphics_item = None

    @property
    def x(self):
        return self.dot.x

    @property
    def y(self):
        return self.dot.y

    @property
    def t(self):
        return self.dot.t


#==============================================================================================
#  Selection handlers
#==============================================================================================

#---------------------------------------------------------------------------------------
class _SingleStrokeSelector(object):

    def __init__(self, graphics_view, strokes):
        self.graphics_view = graphics_view
        self.strokes = [s for s in strokes if len(s.trajectory) > 0]
        self.selected = None

    def clicked(self, values):
        click_coord = values['graph']
        if click_coord[0] is None:
            return
        clicked_stroke = _find_stroke_closest_to(self.strokes, click_coord)
        self._set_clicked_stroke_color(clicked_stroke)

    def _set_clicked_stroke_color(self, clicked_stroke):
        if clicked_stroke == self.selected:
            self.cleanup()
            self.selected = None
        else:
            self.cleanup()
            self.selected = clicked_stroke
            self.highlight_selected(GREEN)

    def highlight_selected(self, color):
        _set_stroke_color(self.selected, color, self.graphics_view)

    def cleanup(self):
        if self.selected is not None:
            _set_stroke_color(self.selected, None, self.graphics_view)


#---------------------------------------------------------------------------------------
class _MultiStrokeSelector(object):
    def __init__(self, graphics_view, characters, select):
        assert select in ('before', 'after')
        self.graphics_view = graphics_view
        self.characters = [c for c in characters if len(c.on_paper_dots) > 0]
        self.strokes = [s for c in characters for s in c.on_paper_strokes]
        self.selected_stroke = None
        self.selected_char = None
        self._get_strokes_to_highlight = self._get_strokes_before if select == 'before' else self._get_strokes_after

    def clicked(self, values):
        click_coord = values['graph']
        if click_coord[0] is None:
            return

        self.cleanup()
        self.selected_char = _find_char_closest_to(self.characters, click_coord)
        if len(self.selected_char.on_paper_strokes) == 1:
            self.selected_char = None
            self.selected_stroke = None
            return
        clicked_stroke = _find_stroke_closest_to(self.selected_char.on_paper_strokes, click_coord)
        self._set_clicked_stroke_color(clicked_stroke)

    def _set_clicked_stroke_color(self, clicked_stroke):
        self.selected_stroke = clicked_stroke
        self.highlight_selected(GREEN)

    def highlight_selected(self, color):
        if self.selected_stroke != self.selected_char.strokes[-1]:
            strokes_to_highlight = self._get_strokes_to_highlight()
        else:
            strokes_to_highlight = [self.selected_stroke]
        for s in strokes_to_highlight:
            _set_stroke_color(s, color, self.graphics_view)

    def _get_strokes_before(self):
        return [s for s in self.selected_char.on_paper_strokes if s.stroke_num <= self.selected_stroke.stroke_num]

    def _get_strokes_after(self):
        return [s for s in self.selected_char.on_paper_strokes if s.stroke_num >= self.selected_stroke.stroke_num]

    def cleanup(self):
        if self.selected_stroke is None:
            return
        for c in self.strokes:
            _set_stroke_color(c, None, self.graphics_view)


#---------------------------------------------------------------------------------------
class _CharSelector(object):

    def __init__(self, graphics_view, characters):
        self.graphics_view = graphics_view
        self.characters = [c for c in characters if len(c.on_paper_dots) > 0]
        self.selected = None

    def clicked(self, values):
        click_coord = values['graph']
        if click_coord[0] is None:
            return
        clicked_char = _find_char_closest_to(self.characters, click_coord)
        self.cleanup()
        self.selected = clicked_char
        self.highlight_selected()

    def highlight_selected(self):
        raise Exception('Implement this method')

    def cleanup(self):
        if self.selected is None:
            return
        _set_chars_color(self.graphics_view, self.characters, None)


#---------------------------------------------------------------------------------------
class _CharsSelectorConsecutivePair(_CharSelector):
    def __init__(self, graphics_view, characters):
        super().__init__(graphics_view, characters)

    def highlight_selected(self):
        if self.selected == self.characters[-1]:
            self.selected = self.characters[-2]
        selected_num = self.selected.char_num
        chars_to_highlight = [c for c in self.characters if selected_num <= c.char_num <= selected_num + 1]
        _set_chars_color(self.graphics_view, chars_to_highlight, GREEN)


#---------------------------------------------------------------------------------------
class _CharSeriesSelector(_CharSelector):
    def __init__(self, graphics_view, characters):
        super().__init__(graphics_view, characters)

    def highlight_selected(self):
        selected_num = self.selected.char_num
        chars_to_highlight = [c for c in self.characters if c.char_num <= selected_num]
        _set_chars_color(self.graphics_view, chars_to_highlight, GREEN)


#---------------------------------------------------------------------------------------
class _CharSelectorAnyPair(object):
    def __init__(self, graphics_view, characters):
        self.graphics_view = graphics_view
        self.characters = [c for c in characters if len(c.on_paper_dots) > 0]
        self.selected_chars = []

    @property
    def n_selected(self):
        selected_char_nums = {c.char_num if c.extends is None else c.extends for c in self.selected_chars}
        return len(selected_char_nums)

    def clicked(self, values):
        click_coord = values['graph']
        if click_coord[0] is None:
            return
        clicked_char = _find_char_closest_to(self.characters, click_coord)
        self.cleanup()
        if clicked_char in self.selected_chars:
            self.unselect_char(clicked_char)
        elif self.n_selected < 2:
            self.select_char(clicked_char)
        self.highlight_selected()

    def select_char(self, clicked_char):
        if clicked_char in self.selected_chars:
            return
        if clicked_char.extends is None:
            self.selected_chars.append(clicked_char)
        else:
            self.selected_chars.extend([c for c in self.characters
                                        if c.char_num == clicked_char.extends or c.extends == clicked_char.extends])

    def unselect_char(self, clicked_char):
        if clicked_char not in self.selected_chars:
            return
        if clicked_char.extends is None:
            self.selected_chars.remove(clicked_char)
        else:
            for c in list(self.selected_chars):
                if c.char_num == clicked_char.extends or c.extends == clicked_char.extends:
                    self.selected_chars.remove(c)

    def highlight_selected(self):
        chars_to_highlight = [c for c in self.characters if c in self.selected_chars]
        _set_chars_color(self.graphics_view, chars_to_highlight, GREEN)

    def cleanup(self):
        _set_chars_color(self.graphics_view, self.characters, None)


#---------------------------------------------------------------------------------------
def _set_chars_color(graphics_view, chars_to_highlight, color):
    for c in chars_to_highlight:
        _set_char_color(c, color, graphics_view)


#=================================================================
# Geometry helpers
#=================================================================

#---------------------------------------------------------------------------------------
def _get_expand_ratio(dots, screen_size, inner_margin, outer_margin):
    """
    Compute the ratio by which dots should be expanded to fill the available x/y area.

    :param dots: list of dot objects
    :param screen_size: Actual screen size (width, height)
    :param inner_margin: The margin required between the most extreme dots and the edges of their plot area
    :param outer_margin: The margin required between the edges of the plot area and screen edges
    """

    x = [dot.x for dot in dots]
    y = [dot.y for dot in dots]
    min_x = min(x)
    min_y = min(y)
    canvas_width = max(x) - min_x + 1
    canvas_height = max(y) - min_y + 1

    needed_width = screen_size[0] - (inner_margin + outer_margin) * 2
    needed_height = screen_size[1] - (inner_margin + outer_margin) * 2
    expand_ratio = min(needed_width / canvas_width, needed_height / canvas_height)

    new_screen_size = round(canvas_width * expand_ratio) + inner_margin * 2, round(canvas_height * expand_ratio) + inner_margin * 2

    return expand_ratio, (min_x, min_y), new_screen_size


#---------------------------------------------------------------------------------------
def _find_dot_closest_to(dots, coord):
    distances = [distance2(d, coord) for d in dots]
    closest = int(np.argmin(distances))  # type: ignore
    return dots[closest]


#---------------------------------------------------------------------------------------
def _find_char_closest_to(characters, coord):

    def char_coord_distance(char):
        return min([distance2(dot, coord) for dot in char.on_paper_dots])

    characters = [c for c in characters]
    distances = [char_coord_distance(c) for c in characters]
    closest = int(np.argmin(distances))  # type: ignore
    return characters[closest]


#---------------------------------------------------------------------------------------
def _find_stroke_closest_to(strokes, coord):

    def stroke_coord_distance(stroke):
        return min([distance2(dot, coord) for dot in stroke.trajectory])

    strokes = [s for s in strokes]
    distances = [stroke_coord_distance(s) for s in strokes]
    closest = int(np.argmin(distances))  # type: ignore
    return strokes[closest]


#---------------------------------------------------------------------------------------
def distance2(dot, coord):
    return (dot.screen_x - coord[0]) ** 2 + (dot.screen_y - coord[1]) ** 2


#---------------------------------------------------------------------------------------
def _set_char_color(char, color, graphics_view):
    for stroke in char.on_paper_strokes:
        _set_stroke_color(stroke, color, graphics_view)


#---------------------------------------------------------------------------------------
def _set_stroke_color(stroke, color, graphics_view):
    if color is None:
        color = stroke.color
    for dot in stroke:  # stroke is iterable over its dots as in original code
        if hasattr(dot, 'ui') and dot.ui is not None:
            dot.ui.setBrush(QBrush(QColor(color)))
            dot.ui.setPen(QPen(QColor(color)))


#---------------------------------------------------------------------------------------
def _set_extending_characters(all_chars, selection_handler):
    if selection_handler.n_selected == 1:
        manip.disconnect_extending_characters(selection_handler.selected_chars)
    else:
        manip.set_extending_characters(all_chars, selection_handler.selected_chars)


def add_copyright(layout):
    uiu.add_copyright_msg(layout, 2020, ['Dror Dotan', 'Maya Yachini'])