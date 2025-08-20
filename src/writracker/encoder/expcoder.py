"""
An application for coding strokes & characters in a full experiment - PyQt5 version
"""
import os
import sys
import traceback
import PyQt5.QtWidgets as qw

import writracker.recorder.results
import writracker.encoder
import writracker.utils as wu


#-------------------------------------------------------------------------------------
def run():
    """
    Run the coding app. Input/output directories are asked using dialogs.
    """

    #-- Create the app; keep the object alive while the UI is running
    app = qw.QApplication.instance() or qw.QApplication(sys.argv)

    raw_exp, raw_exp_dir = _load_raw_exp_ui()
    if raw_exp is None:
        return

    if not wu.is_windows():
        qw.QMessageBox.information(None, 'Select folder', 'Select the encoded-data (results) folder')

    results_dir = choose_directory('Select the encoded-data (results) folder', os.path.dirname(raw_exp_dir))
    if results_dir is None or results_dir == '':
        return

    for trial in raw_exp.trials:
        trial.processed = False

    if not _mark_processed_trials(raw_exp, results_dir):
        return

    try:
        code_experiment(raw_exp.trials, results_dir)

    except Exception as e:
        traceback.print_exception(e)
        qw.QMessageBox.critical(None, 'Error in WEncoder', str(e))


#-------------------------------------------------------------------------------------
def working_directories(raw_input_dir, output_dir):
    input_dir = raw_input_dir
    results_dir = output_dir
    return input_dir, results_dir


#-------------------------------------------------------------------------------------
def current_trial_index(trials, trial_to_start_from):
    return trials, trial_to_start_from


#-------------------------------------------------------------------------------------
def _load_raw_exp_ui():

    while True:

        if not wu.is_windows():
            qw.QMessageBox.information(None, "Select folder",
                                       'Select the raw-data folder (where WRecorder saved the handwriting)')

        raw_dir = choose_directory('Select the raw-data folder (where WRecorder saved the handwriting)', os.path.expanduser('~'))
        if raw_dir is None or raw_dir == '':
            return None, None

        err_msg = writracker.recorder.results.is_invalid_data_directory(raw_dir)
        if err_msg is not None:
            print("Invalid raw-data directory: " + err_msg)
            qw.QMessageBox.critical(None, "Invalid raw-data directory", err_msg)
            continue

        try:
            exp = writracker.recorder.results.load_experiment(raw_dir)
            return exp, raw_dir

        except Exception as e:
            traceback.print_exception(e)
            qw.QMessageBox.critical(None, "Invalid raw-data folder", str(e))


#-------------------------------------------------------------------------------------
def _is_recorder_results_dir(dir_name):
    if writracker.encoder.dataio.is_encoder_results_directory(dir_name):
        return False

    return writracker.recorder.results.is_invalid_data_directory(dir_name) is None


#-------------------------------------------------------------------------------------
def _mark_processed_trials(raw_exp, coded_dir):
    """
    Mark trials that were already coded and should not be coded by default in WEncoder.

    This is done by updating the "processed" property of some trials to False, thereby excluding them.

    Compare raw and results directory. If the experiment was already partially/fully coded, ask user whether
    to recode all/some of the trials, quit, or delete everything and start over.

    Returns True if should proceed, false if should stop.
    """

    raw_trial_nums = tuple(sorted([t.trial_id for t in raw_exp.trials]))

    if not os.path.isfile(writracker.encoder.dataio.trial_index_filename(coded_dir)):
        #-- There is no index file - coding has not started yet
        return raw_exp.trials

    if _is_recorder_results_dir(coded_dir):
        qw.QMessageBox.critical(None, "Invalid folder",
                                "The output directory you selected contains data from a WRecorder (not WEncoder) session. " +
                                "Please choose a separate directory for storing the encoded session.")
        return False

    try:
        coded_trial_nums = writracker.encoder.dataio.load_coded_trials_nums(coded_dir)
    except Exception as e:
        traceback.print_exception(e)
        qw.QMessageBox.critical(None, 'Invalid target directory', f'Error: {e}')
        return False

    coded_trial_nums = tuple(sorted(set(coded_trial_nums)))
    n_coded_trials = len(coded_trial_nums)
    max_coded = max(coded_trial_nums) if n_coded_trials > 0 else 0

    if n_coded_trials == 0:
        return True

    #-- All trials were already coded
    if raw_trial_nums == coded_trial_nums:
        ans = _ask_when_target_directory_contains_data(
            coded_dir, 
            ['The destination folder seems to contains the coding of all trials.',
             'What would you like to do?']
        )
        if ans == 'quit':
            return False
        return True

    #-- Coding has reached the last trial, but some trials are missing along the way
    elif max_coded == max(raw_trial_nums):
        ans = _ask_when_target_directory_contains_data(
            coded_dir, 
            ['The destination folder is not empty.',
             'It looks as if the session was already encoded, but some trials were skipped.'
             'What would you like to do?']
        )
        if ans == 'quit':
            return False

    #-- More coded than raw trials
    elif max_coded > max(raw_trial_nums):
        qw.QMessageBox.critical(None, 'Session was already coded',
                                'The encoded-data folder contains the coding of MORE trials than exist in the session. ' +
                                'It could be that you have selected mismatching directories. ' +
                                'Please verify and re-run WEncoder')
        return False

    #-- All trials up to trial #N were coded. The remaining trials were not
    elif raw_trial_nums[:len(coded_trial_nums)] == coded_trial_nums:
        ans = _ask_when_session_partially_encoded(coded_dir, max_coded, False)
        if ans == 'quit':
            return False

    #-- Coding was done up to trial #N, but some trials were skipped and not coded
    else:
        ans = _ask_when_session_partially_encoded(coded_dir, max_coded, True)
        if ans == 'quit':
            return False

    #-- Here there are 2 alternatives: recode all trials or only some of them
    if ans == 'some':
        for t in raw_exp.trials:
            if t.trial_id in coded_trial_nums:
                t.processed = True

    return True


#-------------------------------------------------------------------------------------
def _ask_when_target_directory_contains_data(coded_dir, question):
    """
    Return a string describing what to do
    """

    while True:
        resp = show_question('Target directory is not empty', question,
                             ["Quit WEncoder", "Delete any encoded trial and start over", "Go on (encoded trials will override previous encoding)"],
                             answers_in_one_line=False)

        if resp == 0:  # Quit WEncoder
            return 'quit'

        elif resp == 1:  # Delete, start over
            reply = qw.QMessageBox.question(None, 'Delete a session', 'This will delete all your previous work. Are you sure?',
                                            qw.QMessageBox.Yes | qw.QMessageBox.No)
            if reply == qw.QMessageBox.Yes:
                writracker.encoder.dataio.delete_all_files_from(coded_dir)
                return 'all'

        elif resp == 2:  # Go on, do nothing
            return 'some'

        else:
            qw.QMessageBox.critical(None, 'Error', 'Error in program (ENC-ASK-01)')
            raise Exception()


#-------------------------------------------------------------------------------------
def _ask_when_session_partially_encoded(coded_dir, last_coded_trial, some_trials_skipped):

    msg = 'The encoded-data folder already contains coding for '
    if last_coded_trial == 1:
        msg += 'trial #1'
    else:
        msg += f'trials #1-{last_coded_trial}'
    if some_trials_skipped:
        msg += ', although some trials were skipped'
    msg += '.'

    while True:
        resp = show_question('Target directory is not empty',
                             ['Some of the trials in this session were already encoded.', msg, 'What do you want to do?'],
                             ['Quit WEncoder', 'Delete any encoded trial and start over', f'Continue encoding from trial {last_coded_trial+1}'],
                             answers_in_one_line=False)

        if resp == 0:   # Quit WEncoder
            return 'quit'

        elif resp == 1:  # Delete, start over
            reply = qw.QMessageBox.question(None, 'Delete a session', 'This will delete all your previous work. Are you sure?',
                                            qw.QMessageBox.Yes | qw.QMessageBox.No)
            if reply == qw.QMessageBox.Yes:
                writracker.encoder.dataio.delete_all_files_from(coded_dir)
                return 'all'

        elif resp == 2:  # Go on, do nothing
            return 'some'


#-------------------------------------------------------------------------------------
def code_experiment(trials, out_dir):

    writracker.encoder.trialcoder.show_settings_screen(show_cancel_button=False)

    i = -1
    reprocess_trial = False
    delta = 1

    coder = writracker.encoder.trialcoder.CodeSingleTrial(out_dir)

    while True:

        i += delta
        if i >= len(trials):
            break

        trial = trials[i]
        if trial.processed and not reprocess_trial:
            continue

        print("trial is: " + str(trial))

        print(f'Processing trial #{i + 1}, source: {trial.source}')
        rc = coder.encode(trial)

        if rc == 'quit':
            return

        elif rc == 'next':
            delta = 1
            reprocess_trial = False

        elif rc == 'prev':
            if i == 0:
                continue
            delta = -1
            reprocess_trial = False

        elif rc == 'choose_trial':
            next_trial = _open_choose_trial(trial, trials)
            i = trials.index(next_trial)
            delta = 0
            reprocess_trial = True

        else:
            raise Exception(f'Invalid RC {rc}')

    if _all_trials_are_coded(out_dir, trials):
        qw.QMessageBox.information(None, 'Finished encoding',
                                   f'Congratulations! You have finished encoding this session. The results are in\n{out_dir}')
    else:
        qw.QMessageBox.information(None, 'Finished encoding',
                                   f'You have finished encoding this session, but not all trials were encoded. The results are in\n{out_dir}')


#-------------------------------------------------------------------------------------
def _all_trials_are_coded(encoded_dir, raw_trials):

    raw_trial_nums = set([t.trial_id for t in raw_trials])

    try:
        coded_trial_nums = writracker.encoder.dataio.load_coded_trials_nums(encoded_dir)
    except Exception as e:
        traceback.print_exception(e)
        qw.QMessageBox.critical(None, 'Error reading the encoded trials', f'Error: {e}')
        return False

    coded_trial_nums = set(coded_trial_nums)

    return raw_trial_nums == coded_trial_nums


#-------------------------------------------------------------------------------------
def _open_choose_trial(curr_trial, all_trials):
    """
    Open the 'choose trial number' window
    """
    
    dialog = ChooseTrialDialog(curr_trial, all_trials)
    
    if dialog.exec_() == qw.QDialog.Accepted:
        return dialog.get_selected_trial()
    else:
        return curr_trial


#-----------------------------------------------------------------------------------------
def show_question(title, question_text, answer_options, answers_in_one_line=True):
    """ Show a question dialog and return the index of the selected answer """
    
    dialog = QuestionDialog(title, question_text, answer_options, answers_in_one_line)
    
    if dialog.exec_() == qw.QDialog.Accepted:
        return dialog.get_result()
    else:
        return -1  # Or handle cancellation appropriately


#----------------------------------------------------------------------------------------
# noinspection PyUnresolvedReferences
class QuestionDialog(qw.QDialog):

    def __init__(self, title, question_text, answer_options, answers_in_one_line=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.answer_options = answer_options
        self.selected_index = -1

        self.setup_ui(question_text, answer_options, answers_in_one_line)

    def setup_ui(self, question_text, answer_options, answers_in_one_line):
        layout = qw.QVBoxLayout()

        # Add question text
        if isinstance(question_text, str):
            question_text = [question_text]

        for text in question_text:
            label = qw.QLabel(text)
            layout.addWidget(label)

        # Add answer buttons
        if answers_in_one_line:
            button_layout = qw.QHBoxLayout()
            for i, option in enumerate(answer_options):
                button = qw.QPushButton(option)
                button.clicked.connect(lambda checked, idx=i: self.select_option(idx))
                button_layout.addWidget(button)
            layout.addLayout(button_layout)
        else:
            for i, option in enumerate(answer_options):
                button = qw.QPushButton(option)
                button.clicked.connect(lambda checked, idx=i: self.select_option(idx))
                layout.addWidget(button)

        self.setLayout(layout)

    def select_option(self, index):
        self.selected_index = index
        self.accept()

    def get_result(self):
        return self.selected_index


#-----------------------------------------------------------------------------------------
# noinspection PyUnresolvedReferences
class ChooseTrialDialog(qw.QDialog):

    #------------------------------------------------------------------------
    def __init__(self, curr_trial, all_trials, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Choose trial')
        self.setModal(True)
        self.curr_trial = curr_trial
        self.all_trials = all_trials
        self.selected_trial = curr_trial
        self.warning_label = None

        self.setup_ui()

    #------------------------------------------------------------------------
    # noinspection PyAttributeOutsideInit
    def setup_ui(self):
        layout = qw.QVBoxLayout()

        # Warning label
        self.warning_label = qw.QLabel()
        self.warning_label.setStyleSheet("color: red; font-size: 18px;")
        layout.addWidget(self.warning_label)

        # Trial selection
        trial_layout = qw.QHBoxLayout()
        trial_layout.addWidget(qw.QLabel('Go to trial number: '))

        self.trial_combo = qw.QComboBox()
        # trial_nums = [t.trial_id for t in self.all_trials]
        trial_desc = [f'{trial.trial_id}: {trial.stimulus}' + (' (already encoded)' if trial.processed else '')
                      for trial in self.all_trials]

        self.trial_combo.addItems(trial_desc)
        curr_trial_ind = self.all_trials.index(self.curr_trial)
        self.trial_combo.setCurrentIndex(curr_trial_ind)

        trial_layout.addWidget(self.trial_combo)
        layout.addLayout(trial_layout)

        # Buttons
        button_layout = qw.QHBoxLayout()
        self.ok_button = qw.QPushButton('OK')
        self.cancel_button = qw.QPushButton('Cancel')

        self.ok_button.clicked.connect(self.validate_and_accept)
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    #------------------------------------------------------------------------
    def validate_and_accept(self):
        try:
            selected_text = self.trial_combo.currentText()
            # Extract trial ID from the description (format: "ID: stimulus...")
            trial_id = int(selected_text.split(':')[0])

            trial_nums = [t.trial_id for t in self.all_trials]

            if not (min(trial_nums) <= trial_id <= max(trial_nums)):
                self.warning_label.setText(f'Invalid trial number (choose a number between {min(trial_nums)} and {max(trial_nums)})')
                return

            if trial_id not in trial_nums:
                self.warning_label.setText('A trial with this number does not exist')
                return

            matching = [t for t in self.all_trials if t.trial_id == trial_id]
            self.selected_trial = matching[0]
            self.accept()

        except (ValueError, IndexError):
            self.warning_label.setText('Invalid trial: please select a valid trial')

    def get_selected_trial(self):
        return self.selected_trial


#------------------------------------------------------------------------
def choose_directory(title, initial_dir=None):
    """ Choose a directory """
    if initial_dir is None:
        initial_dir = os.path.expanduser('~')

    directory = qw.QFileDialog.getExistingDirectory(None, title, initial_dir, qw.QFileDialog.ShowDirsOnly)

    return directory if directory else None
