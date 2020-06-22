import time
from collections import namedtuple
import os
import csv

import PySimpleGUI as sg
from tkinter import messagebox

from encoder import dataiooldrecorder as twio
from encoder.dataiooldrecorder import StartAcquisition, trials_csv_filename
import uiutil as uiu
import utils as u
import data

#----------------------------------------------------------

RecordedPoint = namedtuple('RecordedPoint', ['x', 'y', 'pressure', 'time'])

remaining_targets_filename = 'remaining_targets.csv'

#----------------------------------------------------------
def run():
    """
    Run a full experiment session. Ask experimenter for all info.
    """

    subj_id = uiu.get_subject_id()

    config_fn = uiu.choose_file(title='Select experiment configuration file')
    if config_fn is None:
        return

    try:
        config, targets = twio.load_experiment_config(config_fn)
    except Exception as e:
        messagebox.showerror('Invalid configuration file', str(e))
        raise

    continue_prev = messagebox.askyesno('Continue previous session?', 'Do you want to continue an experiment session that you previously stopped?')
    if continue_prev:
        targets_fn = uiu.choose_file(title='Select the file with targets that should still be run ({:})'.format(remaining_targets_filename))
        if config_fn is None:
            messagebox.showinfo('No file selected', 'You did not select any file, so we start a new session')
        else:
            try:
                targets = _load_remaining_targets(targets_fn)
            except Exception as e:
                messagebox.showerror('Invalid targets file', str(e))
                raise

    out_dir = uiu.choose_directory(title='Select directory for results')
    if out_dir is None:
        return

    trials_out_fn = trials_csv_filename(out_dir, subj_id)
    if os.path.isfile(trials_out_fn):
        n = _nlines(trials_out_fn)
        ok = messagebox.askyesno('Confirm overriding output file',
                                 'The output directory already data of {:} trials. Can I overwrite it?'.format(n - 1))
        if not ok:
            messagebox.showinfo('Please choose another output directory or rename the file')
            return

        twio.reset_trial_info_file(out_dir)

    record(targets, out_dir, start_acquisition_on=config['start_acquisition_on'], beep_on_start=config['beep_on_start'])


#--------------------------------------
def _nlines(filename):
    with open(filename, 'r') as fp:
        n = 0
        for line in fp:
            n += 1
        return n


#----------------------------------------------------------
def record(targets, out_dir, screen_size=None, start_acquisition_on=StartAcquisition.Always, beep_on_start=False):
    """
    Run an experiment session

    :param targets: A list of targets. Each list element is either a string or a dict with 'target' and 'repeated' entries
    :param out_dir: For saving the results. The directory must exist.
    """

    curr_target_num = 0
    trial_id = 1

    exp_start_time = time.time()
    if beep_on_start:
        _beep()

    while curr_target_num < len(targets):

        t = targets[curr_target_num]
        if isinstance(t, str):
            target = t
            repeat_number = 1
        else:
            target = t['target']
            repeat_number = t['repeated']
        rc = record_one_target(trial_id, curr_target_num, target, out_dir, start_acquisition_on, screen_size=screen_size,
                               exp_start_time=exp_start_time, target_repeat_number=repeat_number)
        if rc == 'again':
            pass

        elif rc == 'accept_and_next':
            trial_id += 1
            curr_target_num += 1

        elif rc == 'failed_trial':
            trial_id += 1
            curr_target_num += 1
            targets.append(dict(target=target, repeated=repeat_number + 1))

        elif rc == 'next_trial':
            curr_target_num += 1

        elif rc == 'prev_trial':
            curr_target_num = max(curr_target_num - 1, 0)

        elif rc == 'quit':
            break

        else:
            raise Exception('Error: invalid rc {:}'.format(rc))

        _save_targets_not_yet_processed(targets, out_dir + os.sep + remaining_targets_filename)


#----------------------------------------------------------
def record_one_target(trial_id, target_id, target, out_dir, start_acquisition_on, screen_size=None, exp_start_time=None,
                      target_repeat_number=1):
    """
    Run one trial in the recording session
    """

    if screen_size is None:
        screen_size = uiu.screen_size()
        screen_size = screen_size[0] - 50, screen_size[1] - 150

    window = _create_recording_window(screen_size, trial_id, target_id, target, target_repeat_number)

    acquiring = start_acquisition_on == StartAcquisition.Always
    trial_start_time = None
    trajectory = []

    while True:

        event, values = window.Read(timeout=10)  # timeout is in ms
        if event is None:
            #-- Window closed
            return 'again'

        #-- Nothing done. Update the display
        elif event == sg.TIMEOUT_KEY:
            if acquiring:
                _acquire_data_from_tablet(trajectory)
            else:
                _dismiss_tablet_data()
            #todo update exp_start_time (relative to exp_start_time)

        #-- Quit the app
        elif event in ('q', 'Q', 'quit'):
            window.Close()
            return 'quit'

        #-- Rerun same trial
        elif event in ('r', 'R', 'rerun_trial'):
            window.Close()
            return 'again'

        #-- Return to previous trial
        elif event in ('p', 'P', 'prev_trial'):
            window.Close()
            return 'prev_trial'

        #-- Skip this trial
        elif event in ('k', 'K', 'skip_trial'):
            window.Close()
            return 'prev_trial'

        #-- Skip this trial
        elif event in ('k', 'K', 'skip_trial'):
            window.Close()
            return 'prev_trial'

        #-- Accept this trial
        elif event in ('a', 'A', 'accept'):
            window.Close()
            twio.append_trial(out_dir, trial_id, target_id, target, trajectory, trial_start_time, True)
            return 'accept_and_next'

        #-- Accept this trial, but mark it as "failed" for rerun
        elif event in ('f', 'F', 'fail_trial'):
            window.Close()
            twio.append_trial(out_dir, trial_id, target_id, target, trajectory, trial_start_time, False)
            return 'failed_trial'

        #-- Start acquisition
        elif event in ('s', 'S', 'start_acquire'):
            if start_acquisition_on == StartAcquisition.Always:
                pass

            elif start_acquisition_on == StartAcquisition.Key:
                acquiring = True

            else:
                raise Exception('StartAcquisition mode unknown')


#-------------------------------------------------------------------------------------------------
def _create_recording_window(screen_size, trial_id, target_id, target, target_repeat_number):

    commands = [
        sg.Button('(S)tart acquisition', key='start_acquire'),
        sg.Button('(A)ccept and proceed', key='accept'),
        sg.Button('(R)erun trial', key='rerun_trial'),
        sg.Button('(P)revious trial', key='prev_trial'),
        sg.Button('S(k)ip this trial', key='skip_trial'),
        sg.Button('(F)ailed trial, rerun later', key='fail_trial'),
        sg.Button('(G)to to specific trial', key='choose_trial'),
        sg.Button('(Q)uit experiment', key='quit'),
    ]

    repeat_text = "" if target_repeat_number == 1 else _repeat_text(target_repeat_number)
    title = 'Target #{:}{:}: {:}'.format(target_id, repeat_text, target)

    layout = [
        [sg.Text(title, text_color='green', font=('Arial', 24))],
        [sg.Graph(screen_size, (0, screen_size[1]), (screen_size[0], 0), background_color='Black', key='graph', enable_events=True)],
        commands
    ]

    window = sg.Window('Trial #{:}'.format(trial_id), layout, return_keyboard_events=True)
    window.Finalize()

    return window


#---------------------------------
def _repeat_text(n):
    if n == 1:
        return " (1st time)"
    elif n == 2:
        return ' (2nd time)'
    elif n == 3:
        return ' (3rd time)'
    else:
        return " ({:}th time)".format(n)


#-------------------------------------------------------------------------------------------------
def _save_targets_not_yet_processed(targets, filename):
    with open(filename, 'w') as fp:
        writer = csv.DictWriter(fp, ['target', 'repeated'], lineterminator=u.newline())
        writer.writeheader()
        for target in targets:
            writer.writerow(target)


#-------------------------------------------------------------------------------------------------
def _beep():
    #todo fix this
    pass
