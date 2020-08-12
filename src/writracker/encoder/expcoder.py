"""
An application for coding strokes & characters in a full experiment
"""
import os
# noinspection PyPep8Naming
import PySimpleGUI as sg
from tkinter import messagebox
import tkinter as tk

from writracker import encoder
from writracker.encoder import dataiooldrecorder
from writracker.encoder.trialcoder import encode_one_trial
from writracker import uiutil as uiu


#-------------------------------------------------------------------------------------
def run():
    """
    Run the coding app. Input/output directories are asked using dialogs.
    """

    root = tk.Tk()
    root.withdraw()

    raw_exp = _load_raw_exp_ui()
    if raw_exp is None:
        return

    results_dir = uiu.choose_directory('Select the encoded-data (results) folder')
    if results_dir is None or results_dir == '':
        return

    which_trials_to_code = _trials_to_code(raw_exp, results_dir)

    if isinstance(which_trials_to_code, int):
        trials_to_code = raw_exp.trials

    elif which_trials_to_code:
        trials_to_code = raw_exp.trials

    else:
        return

    # try:
    code_experiment(trials_to_code, results_dir)

    # except Exception as e:
    #     messagebox.showerror('Error in coding app', str(e))


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
        raw_dir = uiu.choose_directory("Select the raw-data folder (where WRecorder saved the handwriting)")
        if raw_dir is None or raw_dir == '':
            return None

        err_msg = dataiooldrecorder.is_invalid_data_directory(raw_dir)
        if err_msg is not None:  # check if there suppose to be "not" before None
            print("Invalid raw-data directory")
            messagebox.showerror("Invalid raw-data directory", err_msg)
            return None

        #try:
        exp = dataiooldrecorder.load_experiment(raw_dir)
        #print("try")
        return exp

        '''except Exception as e:
            print("Invalid raw-data directory 2")
            messagebox.showerror("Invalid raw-data directory 2", str(e))'''


#-------------------------------------------------------------------------------------
def _trials_to_code(raw_exp, coded_dir):
    """
    Compare raw and results directory. If the experiment was already partially/fully coded, ask user whether
    she wants to recode all trials.
    """

    raw_trial_nums = tuple(sorted([t.trial_id for t in raw_exp.trials]))


    if not os.path.isfile(encoder.dataio.trial_index_filename(coded_dir)):
        #-- There is no index file - coding has not started yet
        print("no index file")
        return True

    coded_trials = encoder.dataio.load_trials_index(coded_dir)
    coded_trial_nums = tuple(sorted(set([t['trial_id'] for t in coded_trials])))
    try:
        max_coded = max(coded_trial_nums)
    except:
        messagebox.showerror('Session was already coded', 'Please delete all files from the encoded-data folder and re-run WEncoder')
        return False

    #-- All trials were already coded
    if raw_trial_nums == coded_trial_nums:
        messagebox.showerror('Session was already coded',
                             'The encoded-data folder seems to contains the coding of all trials. ' +
                             'To encode the session again, delete all files from the encoded-data folder and re-run WEncoder)')
        return False


    #-- Coding has reached the last trial, but some trials are missing along the way
    elif max_coded == max(raw_trial_nums):
        messagebox.showerror('Session was already coded',
                             'The encoded-data folder contains the session''s coding, but the coding has skipped some trials. ')
        return False

    #-- More coded than raw trials
    elif max_coded > max(raw_trial_nums):
        messagebox.showerror('Session was already coded',
                             'The encoded-data folder contains the coding of MORE trials than exist in the session. ' +
                             'It could be that you have selected mismatching directories. ' +
                             'Please verify and re-run WEncoder')
        return False

    #-- All trials up to trial #N were coded, but some trials were not coded yet
    elif raw_trial_nums[:len(coded_trial_nums)] == coded_trial_nums:
        ans = messagebox.askquestion('Session was already coded',
                                     'The encoded-data folder already contains coding for trials 1-{:}. '.format(max_coded) +
                                     'Do you want to continue coding from trial #{:}?'.format(max_coded + 1))
        if ans:
            return max_coded + 1
        else:
            return False

    #-- Coding was done up to trial #N, but some trials were skipped and not coded
    else:
        ans = messagebox.askquestion('Session was already coded',
                                     'The encoded-data folder contains the coding of trials up to {:}, '.format(max_coded) +
                                     'but the coding has skipped some trials. ' +
                                     'Do you want to continue coding from trial #{:}?'.format(max_coded + 1))
        if ans:
            return max_coded + 1
        else:
            return False


#-------------------------------------------------------------------------------------



def code_experiment(trials, out_dir):

    i = 0
    while i < len(trials):


        trial = trials[i]
        print("trial is: " + str(trial))
        encoder.dataio.remove_from_trial_index(out_dir, trial.trial_id)

        print('Processing trial #{}, source: {}'.format(i + 1, trial.source))
        rc = encode_one_trial(trial, out_dir)

        if rc == 'quit':
            break

        elif rc == 'next':
            # f i == (len(trials)-1):
            #     continue
            i += 1


        elif rc == 'prev':
            if i == 0:
                continue
            i -= 1


        elif rc == 'choose_trial':
            next_trial = _open_choose_trial(trial, trials)
            i = trials.index(next_trial)

        else:
            raise Exception('Invalid RC {:}'.format(rc))


#-------------------------------------------------------------------------------------
def _open_choose_trial(curr_trial, all_trials):
    """
    Open the 'settings' window
    """

    trial_nums = [t.trial_id for t in all_trials]

    show_popup = True
    warning = ''

    while show_popup:

        layout = [
            [sg.Text(warning, text_color='red', font=('Arial', 18))],
            [sg.Text('Go to trial number: '), sg.InputText(str(curr_trial.trial_id)),
             sg.Text('({:} - {:})'.format(min(trial_nums), max(trial_nums)))],
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
                trial_id = int(values[0])
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
