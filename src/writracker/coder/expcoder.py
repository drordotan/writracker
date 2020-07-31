"""
An application for coding strokes & characters in a full experiment
"""
import os
import PySimpleGUI as sg
from tkinter import messagebox
import tkinter as tk
import traceback

from writracker.encoder.trialcoder import encode_one_trial as _markup_one_trial
import writracker as wt
import writracker.uiutil as uiu


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
    results_dir = uiu.choose_directory('Select the directory for the results (coded data) hello')
    if results_dir is None or results_dir == '':
        return

    which_trials_to_code = _trials_to_code(raw_exp, results_dir)

    if isinstance(which_trials_to_code, int):
        trials_to_code = [t for t in raw_exp.trials if t.trial_id >= which_trials_to_code]

    elif which_trials_to_code:
        trials_to_code = raw_exp.trials

    else:
        return

    # try:
    code_experiment(trials_to_code, results_dir)
    # except Exception as e:
    #     messagebox.showerror('Error in coding app', str(e))


#-------------------------------------------------------------------------------------
def _load_raw_exp_ui():

    while True:
        raw_dir = uiu.choose_directory("Select the directory of the experiment's raw results")
        if raw_dir is None or raw_dir == '':
            return None

        err_msg = wt.recorder.dataio.is_invalid_data_directory(raw_dir)
        if err_msg is not None:                                         #check if there suppose to be "not" before None
            print("Invalid raw-data directory 11")
            messagebox.showerror("Invalid raw-data directory 1", err_msg)
            return None

        #try:
        exp = wt.recorder.dataio.load_experiment(raw_dir)
        print("try")
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


    print("coded dir is: " + str(coded_dir))
    print(raw_exp)

    if not os.path.isfile(wt.encoder.dataio.trial_index_filename(coded_dir)):
        #-- There is no index file - coding has not started yet
        print("no index file")
        return True

    coded_trials = wt.encoder.dataio.load_trials_index(coded_dir)
    coded_trial_nums = tuple(sorted(set([t['trial_id'] for t in coded_trials])))
    print(coded_trial_nums)
    print(coded_trials)
    print("value error")
    max_coded = max(coded_trial_nums)
    print("max coded: " + str(max_coded))

    #-- All trials were already coded
    if raw_trial_nums == coded_trial_nums:
        messagebox.showerror('Experiment was already coded',
                             'The results directory seems to contains the coding of all trials. ' +
                             'To recode the experiment, delete all files from the results directory and re-run the program')
        return False


    #-- Coding has reached the last trial, but some trials are missing along the way
    elif max_coded == max(raw_trial_nums):
        messagebox.showerror('Experiment was already coded',
                             'The results directory contains the experiment''s coding, but the coding has skipped some trials. ')
        return False

    #-- More coded than raw trials
    elif max_coded > max(raw_trial_nums):
        messagebox.showerror('Experiment was already coded',
                             'The results directory contains the coding of MORE trials than exist in the raw experiment. ' +
                             'It could be that you have selected mismatching directories. ' +
                             'Please verify and re-run the program')
        return False

    #-- All trials up to trial #N were coded, but some trials were not coded yet
    elif raw_trial_nums[:len(coded_trial_nums)] == coded_trial_nums:
        ans = messagebox.askquestion('Experiment was already coded',
                                     'The results directory contains the coding of trials up to {:}. '.format(max_coded) +
                                     'Do you want to continue coding from trial #{:}?'.format(max_coded + 1))
        if ans:
            return max_coded + 1
        else:
            return False

    #-- Coding was done up to trial #N, but some trials were skipped and not coded
    else:
        ans = messagebox.askquestion('Experiment was already coded',
                                     'The results directory contains the coding of trials up to {:}, '.format(max_coded) +
                                     'but the coding has skipped some trials. ' +
                                     'Do you want to continue coding from trial #{:}?'.format(max_coded + 1))
        if ans:
            return max_coded + 1
        else:
            return False


#-------------------------------------------------------------------------------------
def run_mccloskey():
    """
    Run the app with full UI. Ask the user for any relevant info.
    Input files are in McCloskey's format.
    """
    root = tk.Tk()
    root.withdraw()

    raw_dir = uiu.choose_directory('Select the directory with the experiment raw data')
    print("raw dir is: " + str(raw_dir))
    #raw_dir = "C:\Users\Ron\Documents\GitHub\new\raw"
    if raw_dir is None:

        return

    prefixes = _get_mccloskey_prefixes(raw_dir)

    if prefixes is None:
        return

    results_dir = uiu.choose_directory('Select the directory for the results (coded data)')
    #results_dir = "C:\Users\Ron\Documents\GitHub\new\results"
    if results_dir is None:
        return
    rc = messagebox.askokcancel('Validate',
                                'Input directory: ' + raw_dir +
                                '\nResults directory: ' + results_dir +
                                '\nPlease double-check this. Any existing data in the results directory may be overriden.')
    if not rc:
        return

    raw_exp = wt.mccloskey.rawreader.load_experiment(raw_dir, prefixes)

    which_trials_to_code = _trials_to_code(raw_exp, results_dir)
    if isinstance(which_trials_to_code, int):
        trials_to_code = [t for t in raw_exp.trials if t.trial_id >= which_trials_to_code]

    elif which_trials_to_code:
        trials_to_code = raw_exp.trials

    else:
        return

    try:
        code_experiment(trials_to_code, results_dir)
    except Exception as e:
        traceback.print_exc()
        messagebox.showerror('Error in coding app', str(e))



#-------------------------------------------------------------------------------------
def _get_mccloskey_prefixes(dir_name):

    all_prefixes = wt.mccloskey.rawreader.get_existing_prefixes(dir_name)
    if len(all_prefixes) == 0:
        messagebox.showerror('Invalid directory', 'No raw data was found in the selected directory')
        return None

    all_prefixes = list(all_prefixes)

    layout = [
        [sg.Text('Choose the file prefixes you want to include, in order:', font=('Arial', 18))],
    ]

    for i, prefix in enumerate(all_prefixes):
        desc = sg.Text("{:}. ".format(i + 1), font=('Arial', 18))
        selection = sg.DropDown(['-'] + all_prefixes, readonly=True)
        layout.append([desc, selection])

    layout.append([sg.Button('OK'), sg.Button('Cancel')])

    while True:
        window = sg.Window('Choose sessions for markup', layout)
        event, values = window.Read()

        window.Close()

        if event is None or event == 'Cancel':
            return None

        selected_prefixes = [v for v in values.values() if v is not None and v != '-']
        print(selected_prefixes)

        if len(selected_prefixes) == len(set(selected_prefixes)):
            #-- OK, no duplicates
            return selected_prefixes

        messagebox.showerror('Invalid selection', 'Please do not selecte the same file prefix twice')


#-------------------------------------------------------------------------------------
def code_experiment(trials, out_dir):

    print("trials are: " + str(trials))
    i = 0
    while i < len(trials):


        trial = trials[i]
        print("trial is: " + str(trial))
        wt.encoder.dataio.remove_from_trial_index(out_dir, trial.trial_id)

        print('Processing trial #{}, source: {}'.format(i + 1, trial.source))
        rc = _markup_one_trial(trial, out_dir)

        if rc == 'quit':
            break

        elif rc == 'next':
            if i == (len(trials)-1):
                continue
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
