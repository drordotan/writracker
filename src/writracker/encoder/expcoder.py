"""
An application for coding strokes & characters in a full experiment
"""
import os
import traceback
# noinspection PyPep8Naming
import PySimpleGUI as sg
from tkinter import messagebox
import tkinter as tk

import writracker.recorder.results
import writracker.encoder
from writracker import uiutil as uiu


#-------------------------------------------------------------------------------------
def run():
    """
    Run the coding app. Input/output directories are asked using dialogs.
    """

    root = tk.Tk()
    root.withdraw()

    raw_exp, raw_exp_dir = _load_raw_exp_ui()
    if raw_exp is None:
        return

    results_dir = uiu.choose_directory('Select the encoded-data (results) folder', os.path.dirname(raw_exp_dir))
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
        messagebox.showerror('Error in WEncoder', str(e))


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
        raw_dir = uiu.choose_directory("Select the raw-data folder (where WRecorder saved the handwriting)", initial_dir=os.path.expanduser('~'))
        if raw_dir is None or raw_dir == '':
            return None, None

        err_msg = writracker.recorder.results.is_invalid_data_directory(raw_dir)
        if err_msg is not None:  # check if there suppose to be "not" before None
            print("Invalid raw-data directory: " + err_msg)
            messagebox.showerror("Invalid raw-data directory", err_msg)
            return None, None

        try:
            exp = writracker.recorder.results.load_experiment(raw_dir)
            return exp, raw_dir

        except Exception as e:
            traceback.print_exception(e)
            messagebox.showerror("Invalid raw-data folder", str(e))


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
        messagebox.showerror("Invalid folder",
                             "The output directory you selected contains data from a WRecorder (not WEncoder) session. " +
                             "Please choose a separate directory for storing the encoded session.")
        return False

    try:
        coded_trial_nums = writracker.encoder.dataio.load_coded_trials_nums(coded_dir)
    except Exception as e:
        traceback.print_exception(e)
        messagebox.showerror('Invalid target directory', 'Error: {}'.format(e))
        return False

    coded_trial_nums = tuple(sorted(set(coded_trial_nums)))
    n_coded_trials = len(coded_trial_nums)
    max_coded = max(coded_trial_nums) if n_coded_trials > 0 else 0

    if n_coded_trials == 0:
        return True

    #-- All trials were already coded
    if raw_trial_nums == coded_trial_nums:

        ans = _ask_when_target_directory_contains_data(coded_dir, ['The destination folder seems to contains the coding of all trials.',
                                                                   'What would you like to do?'])
        if ans == 'quit':
            return False

        return True

    #-- Coding has reached the last trial, but some trials are missing along the way
    elif max_coded == max(raw_trial_nums):
        ans = _ask_when_target_directory_contains_data(coded_dir, ['The destination folder is not empty.',
                                                                   'It looks as if the session was already encoded, but some trials were skipped.'
                                                                   'What would you like to do?'])
        if ans == 'quit':
            return False

    #-- More coded than raw trials
    elif max_coded > max(raw_trial_nums):
        messagebox.showerror('Session was already coded',
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
    Return a string desribing what to do
    """

    while True:
        resp = show_question('Target directory is not empty',
                             question, ["Quit WEncoder", "Delete any encoded trial and start over",
                                        "Go on (encoded trials will override previous encoding)"],
                             answers_in_one_line=False)
        if resp == 0:  # Quit WEncoder
            return 'quit'

        elif resp == 1:  # Delete, start over
            # -- verify
            ans = messagebox.askquestion('Delete a session', 'This will delete all your previous work. Are you sure?')
            if ans == 'yes':
                writracker.encoder.dataio.delete_all_files_from(coded_dir)
                return 'all'

        elif resp == 2:  # Go on, do nothing
            return 'some'

        else:
            messagebox.showerror('Error', 'Error in program (ENC-ASK-01)')
            raise Exception()


#-------------------------------------------------------------------------------------
def _ask_when_session_partially_encoded(coded_dir, last_coded_trial, some_trials_skipped):

    msg = 'The encoded-data folder already contains coding for '
    if last_coded_trial == 1:
        msg += 'trial #1'
    else:
        msg += 'trials #1-{}'.format(last_coded_trial)
    if some_trials_skipped:
        msg += ', although some trials were skipped'
    msg += '.'

    while True:
        resp = show_question('Target directory is not empty',
                             ['Some of the trials in this session were already encoded.', msg, 'What do you want to do?'],
                             ["Quit WEncoder", "Delete any encoded trial and start over", "Start encoding from trial {}".format(last_coded_trial+1)],
                             answers_in_one_line=False)
        if resp == 0:   # Quit WEncoder
            return 'quit'

        elif resp == 1:  # Delete, start over
            # -- verify
            ans = messagebox.askquestion('Delete a session', 'This will delete all your previous work. Are you sure?')
            if ans == 'yes':
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

    while True:

        i += delta
        if i >= len(trials):
            break

        trial = trials[i]
        if trial.processed and not reprocess_trial:
            continue

        print("trial is: " + str(trial))

        print('Processing trial #{}, source: {}'.format(i + 1, trial.source))
        rc = writracker.encoder.trialcoder.encode_one_trial(trial, out_dir)

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
            raise Exception('Invalid RC {:}'.format(rc))

    if _all_trials_are_coded(out_dir, trials):
        messagebox.showinfo('Finished encoding',
                            'Congratulations! You have finished encoding this session. The results are in\n{}'.format(out_dir))
    else:
        messagebox.showinfo('Finished encoding',
                            'You have finished encoding this session, but not all trials were encoded. The results are in\n{}'.format(out_dir))


#-------------------------------------------------------------------------------------
def _all_trials_are_coded(encoded_dir, raw_trials):

    raw_trial_nums = set([t.trial_id for t in raw_trials])

    try:
        coded_trial_nums = writracker.encoder.dataio.load_coded_trials_nums(encoded_dir)
    except Exception as e:
        traceback.print_exception(e)
        messagebox.showerror('Error reading the encoded trials', 'Error: {}'.format(e))
        return False

    coded_trial_nums = set(coded_trial_nums)

    return raw_trial_nums == coded_trial_nums


#-------------------------------------------------------------------------------------
def _open_choose_trial(curr_trial, all_trials):
    """
    Open the 'choose trial number' window
    """

    trial_nums = [t.trial_id for t in all_trials]
    trial_desc = ["{}: {}{}".format(t.trial_id, t.stimulus, " (already encoded)" if t.processed else "") for t in all_trials]
    trial_desc_to_num = {d: n for d, n in zip(trial_desc, trial_nums)}

    curr_trial_ind = all_trials.index(curr_trial)

    show_popup = True
    warning = ''

    while show_popup:

        layout = [
            [sg.Text(warning, text_color='red', font=('Arial', 18))],
            [sg.Text('Go to trial number: '), sg.DropDown(trial_desc, default_value=trial_desc[curr_trial_ind], readonly=True)],
            [sg.Button('OK'), sg.Button('Cancel')],
        ]

        window = sg.Window('Choose trial', layout)

        event = None
        apply = False
        values = ()

        while event is None:
            event, values = window.Read()
            apply = event == 'OK'

        window.Close()

        if apply:
            try:
                trial_id = trial_desc_to_num[values[0]]
            except ValueError:
                warning = 'Invalid trial: please write a whole number'
                continue

            if not (min(trial_nums) <= trial_id <= max(trial_nums)):
                warning = 'Invalid trial number (choose a number between {:} and {:}'.format(min(trial_nums), max(trial_nums))
                continue

            if trial_id not in trial_nums:
                warning = 'A trial with this number does not exist'
                continue

            matching = [t for t in all_trials if t.trial_id == trial_id]
            return matching[0]

        else:
            return curr_trial


#-----------------------------------------------------------------------------------------
def show_question(title, question_text, answer_options, answers_in_one_line=True):

    if isinstance(question_text, str):
        question_text = [question_text]

    layout = [[sg.Text(t)] for t in question_text]

    if answers_in_one_line:
        layout.append([sg.Button(a) for a in answer_options])
    else:
        for a in answer_options:
            layout.append([sg.Button(a)])

    window = sg.Window(title, layout)

    event = None
    while event is None:
        event, values = window.Read()

    window.Close()

    return answer_options.index(event)
